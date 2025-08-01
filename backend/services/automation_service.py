import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from models.task import Task, TaskStatus, TaskStep
from .ip_service import IPService
from .message_service import get_message_service
from .message_service_sota import get_sota_message_service

logger = logging.getLogger(__name__)

class AutomationService:
    """基于apple_automator.py的自动化服务 - 完全重写版本"""
    
    def __init__(self, ip_service=None):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Page] = {}
        self.websocket_handler = None
        # 🚀 优化：使用传入的IP服务或延迟初始化
        self.ip_service = ip_service
        if self.ip_service is None:
            # 延迟初始化，避免启动时阻塞
            self.ip_service = IPService(rotation_enabled=True)
        # 初始化消息服务（兼容旧版本）
        self.message_service = get_message_service()
        # 🚀 初始化SOTA消息服务
        self.sota_message_service = get_sota_message_service()
        
    def set_websocket_handler(self, handler):
        """设置WebSocket处理器用于实时反馈"""
        self.websocket_handler = handler
    
    def _send_step_update(self, task: Task, step: str, status: str, progress: float = None, message: str = ""):
        """发送步骤更新到前端 - 确保任务状态正确更新 - 高频率同步版本"""
        try:
            # 🚀 根据step更新任务的实际状态
            if step == TaskStep.STAGE_1_PRODUCT_CONFIG.value:
                task.status = TaskStatus.STAGE_1_PRODUCT_CONFIG
            elif step == TaskStep.STAGE_2_ACCOUNT_LOGIN.value:
                task.status = TaskStatus.STAGE_2_ACCOUNT_LOGIN
            elif step == TaskStep.STAGE_3_ADDRESS_PHONE.value:
                task.status = TaskStatus.STAGE_3_ADDRESS_PHONE
            elif step == TaskStep.STAGE_4_GIFT_CARD.value:
                if status == "paused" or "等待" in message:
                    task.status = TaskStatus.WAITING_GIFT_CARD_INPUT
                else:
                    task.status = TaskStatus.STAGE_4_GIFT_CARD

            # 更新任务步骤和进度
            task.current_step = step
            if progress is not None:
                task.progress = progress

            # 🚀 立即多重同步 - 确保快速响应
            import asyncio
            import time
            
            # 1. SOTA实时同步服务（最高优先级）
            try:
                from services.realtime_sync_service import get_realtime_sync_service
                realtime_service = get_realtime_sync_service()
                if realtime_service:
                    realtime_service.publish_step_update(
                        task_id=task.id,
                        step=step,
                        status=status,
                        progress=progress or task.progress,
                        message=message
                    )
                    realtime_service.publish_task_status(
                        task_id=task.id,
                        status=task.status.value,
                        progress=task.progress,
                        message=message
                    )
            except Exception as e:
                logger.warning(f"⚠️ SOTA同步失败: {e}")
            
            # 2. 立即WebSocket广播
            if self.websocket_handler:
                self.websocket_handler.broadcast('task_update', task.to_dict())
                if progress is None:
                    progress = task.progress
                self.websocket_handler.send_step_update(task.id, step, status, progress, message)
            
            # 3. 立即Redis同步
            if hasattr(self, 'message_service') and self.message_service:
                status_value = task.status.value if hasattr(task.status, 'value') else str(task.status)
                self.message_service.sync_task_status(
                    task_id=task.id,
                    status=status_value,
                    progress=task.progress,
                    message=f"{step}: {message}" if message else step
                )

                # 发送步骤更新事件
                self.message_service.publish('step_update', {
                    'task_id': task.id,
                    'step': step,
                    'status': status,
                    'progress': progress or task.progress,
                    'message': message,
                    'timestamp': time.time()
                })

            # 4. SOTA消息服务
            if hasattr(self, 'sota_message_service') and self.sota_message_service:
                self.sota_message_service.send_step_update(
                    task_id=task.id,
                    step=step,
                    status=status,
                    progress=progress,
                    message=message
                )

            logger.info(f"✅ SOTA高频率步骤更新已同步: {task.id} - {step} ({status}) - 任务状态: {task.status}")

        except Exception as e:
            logger.error(f"❌ 发送步骤更新失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _send_log(self, task: Task, level: str, message: str):
        """发送日志到前端 - SOTA版本"""
        try:
            # 添加到任务日志
            task.add_log(message, level)

            # 🚀 使用SOTA消息服务
            self.sota_message_service.sync_task_log(task.id, level, message)

            # 兼容旧版本
            self.message_service.sync_task_log(task.id, level, message)

            logger.info(f"✅ 日志已同步: {task.id} - [{level}] {message}")

            # 保持向后兼容
            if self.websocket_handler:
                self.websocket_handler.send_task_log(task.id, level, message)

        except Exception as e:
            logger.error(f"❌ 发送日志失败: {e}")

    async def execute_task(self, task: Task) -> bool:
        """🚀 执行四阶段任务流程 - 主入口方法"""
        try:
            self._send_log(task, "info", f"🚀 开始执行任务: {task.config.name}")

            # 初始化浏览器
            if not await self.initialize(task):
                return False

            # 🎯 阶段1：产品配置
            if not await self._execute_stage_1_product_config(task):
                return False

            # 🎯 阶段2：账号登录
            if not await self._execute_stage_2_account_login(task):
                return False

            # 🎯 阶段3：地址电话配置
            if not await self._execute_stage_3_address_phone(task):
                return False

            # 🎯 阶段4：礼品卡配置 - 这里会暂停等待用户输入
            if not await self._execute_stage_4_gift_card(task):
                return False

            self._send_log(task, "success", "✅ 任务执行完成")
            return True

        except Exception as e:
            self._send_log(task, "error", f"❌ 任务执行失败: {str(e)}")
            logger.error(f"任务执行失败: {str(e)}")
            return False
        finally:
            # 注意：不要在这里清理资源，因为用户可能还需要在浏览器中操作
            pass

    # 🚀 四阶段执行方法
    async def _execute_stage_1_product_config(self, task: Task) -> bool:
        """阶段1：产品配置"""
        try:
            # 🚀 更新任务状态为阶段1
            task.status = TaskStatus.STAGE_1_PRODUCT_CONFIG
            self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "started", 25, "开始产品配置阶段")

            # 导航到产品页面
            if not await self.navigate_to_product(task):
                task.status = TaskStatus.FAILED
                self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "failed", 25, "导航到产品页面失败")
                return False

            # 配置产品选项
            if not await self.configure_product(task):
                task.status = TaskStatus.FAILED
                self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "failed", 25, "产品配置失败")
                return False

            # 添加到购物车
            if not await self.add_to_bag(task):
                task.status = TaskStatus.FAILED
                self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "failed", 25, "添加到购物车失败")
                return False

            self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "completed", 25, "✅ 产品配置阶段完成")
            self._send_log(task, "success", "🎉 阶段1：产品配置 - 成功完成")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            self._send_step_update(task, TaskStep.STAGE_1_PRODUCT_CONFIG.value, "failed", 25, f"产品配置阶段失败: {str(e)}")
            self._send_log(task, "error", f"❌ 阶段1失败: {str(e)}")
            return False

    async def _execute_stage_2_account_login(self, task: Task) -> bool:
        """阶段2：账号登录 - 现在登录已在阶段1的checkout中处理"""
        try:
            # 🚀 更新任务状态为阶段2
            task.status = TaskStatus.STAGE_2_ACCOUNT_LOGIN
            self._send_step_update(task, TaskStep.STAGE_2_ACCOUNT_LOGIN.value, "started", 50, "开始账号登录阶段")

            # 获取页面对象
            page = self.pages.get(task.id)
            if not page:
                raise Exception("浏览器页面不可用")

            # 检查当前页面状态，确认登录是否已完成
            current_url = page.url
            page_title = await page.title()
            task.add_log(f"阶段2检查 - 当前URL: {current_url}", "info")
            task.add_log(f"阶段2检查 - 页面标题: {page_title}", "info")

            # 检测页面状态
            page_state = await self._detect_page_state(page)
            task.add_log(f"阶段2检查 - 页面状态: {page_state}", "info")

            if page_state == "checkout_page" or "checkout" in current_url.lower() or "billing" in current_url.lower():
                task.add_log("✅ 登录已完成，当前在结账页面", "success")
            elif page_state == "already_logged_in":
                task.add_log("✅ 检测到已登录状态", "success")
            else:
                # 如果还没有登录，尝试登录
                task.add_log("⚠️ 登录可能未完成，尝试处理登录", "warning")
                await self._handle_apple_login(page, task)

            self._send_step_update(task, TaskStep.STAGE_2_ACCOUNT_LOGIN.value, "completed", 50, "✅ 账号登录阶段完成")
            self._send_log(task, "success", "🎉 阶段2：账号登录 - 成功完成")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            self._send_step_update(task, TaskStep.STAGE_2_ACCOUNT_LOGIN.value, "failed", 50, f"账号登录阶段失败: {str(e)}")
            self._send_log(task, "error", f"❌ 阶段2失败: {str(e)}")
            return False

    async def _execute_stage_3_address_phone(self, task: Task) -> bool:
        """阶段3：地址电话配置"""
        try:
            # 🚀 更新任务状态为阶段3
            task.status = TaskStatus.STAGE_3_ADDRESS_PHONE
            self._send_step_update(task, TaskStep.STAGE_3_ADDRESS_PHONE.value, "started", 75, "开始地址电话配置阶段")

            # 获取页面对象
            page = self.pages.get(task.id)
            if not page:
                raise Exception("浏览器页面不可用")

            # 获取账号配置中的电话号码
            account_config = task.config.account_config
            phone_number = account_config.phone_number if account_config else '07700900000'

            # 继续结账流程（包括地址和电话号码配置）
            await self._continue_checkout_flow(page, task, phone_number)

            self._send_step_update(task, TaskStep.STAGE_3_ADDRESS_PHONE.value, "completed", 75, "✅ 地址电话配置阶段完成")
            self._send_log(task, "success", "🎉 阶段3：地址电话配置 - 成功完成")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            self._send_step_update(task, TaskStep.STAGE_3_ADDRESS_PHONE.value, "failed", 75, f"地址电话配置阶段失败: {str(e)}")
            self._send_log(task, "error", f"❌ 阶段3失败: {str(e)}")
            return False

    async def _execute_stage_4_gift_card(self, task: Task) -> bool:
        """阶段4：礼品卡配置"""
        try:
            # 🚀 更新任务状态为阶段4
            task.status = TaskStatus.STAGE_4_GIFT_CARD
            self._send_step_update(task, TaskStep.STAGE_4_GIFT_CARD.value, "started", 100, "开始礼品卡配置阶段")

            # 获取页面对象
            page = self.pages.get(task.id)
            if not page:
                raise Exception("浏览器页面不可用")

            # 检查是否已经有礼品卡信息（用户已经输入过）
            if task.config.gift_cards or task.config.gift_card_code:
                task.add_log("🎁 检测到已有礼品卡信息，直接应用礼品卡", "info")
                # 直接应用礼品卡，不再等待用户输入
                await self._apply_existing_gift_cards(page, task)
            else:
                task.add_log("🎁 没有礼品卡信息，等待用户输入", "info")
                # 处理礼品卡输入（这里会暂停等待用户输入）
                await self._handle_gift_card_input(page, task)

            # 如果到达这里，说明礼品卡处理完成
            self._send_step_update(task, TaskStep.STAGE_4_GIFT_CARD.value, "completed", 100, "✅ 礼品卡配置阶段完成")
            self._send_log(task, "success", "🎉 阶段4：礼品卡配置 - 成功完成")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            self._send_step_update(task, TaskStep.STAGE_4_GIFT_CARD.value, "failed", 100, f"礼品卡配置阶段失败: {str(e)}")
            self._send_log(task, "error", f"❌ 阶段4失败: {str(e)}")
            return False

    async def initialize(self, task: Task) -> bool:
        """初始化Playwright"""
        try:
            self._send_step_update(task, "initializing", "started", message="正在启动浏览器...")
            self._send_log(task, "info", "🚀 正在初始化浏览器...")

            self.playwright = await async_playwright().start()
            self._send_step_update(task, "initializing", "progress", 30, "Playwright已启动")
            
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self._send_step_update(task, "initializing", "progress", 80, "浏览器已启动")

            self._send_log(task, "success", "✅ Playwright初始化成功")
            self._send_step_update(task, "initializing", "completed", 100, "初始化完成")
            logger.info("Playwright初始化成功")
            return True
        except Exception as e:
            self._send_log(task, "error", f"❌ Playwright初始化失败: {str(e)}")
            self._send_step_update(task, "initializing", "failed", message=f"初始化失败: {str(e)}")
            logger.error(f"Playwright初始化失败: {str(e)}")
            return False
    
    async def navigate_to_product(self, task: Task) -> bool:
        """导航到产品URL"""
        try:
            # 创建新的浏览器上下文和页面
            context = await self.browser.new_context(locale="en-GB")
            page = await context.new_page()
            
            self.contexts[task.id] = context
            self.pages[task.id] = page
            
            task.add_log(f"🌐 正在导航到: {task.config.url}", "info")
            await page.goto(task.config.url, wait_until='domcontentloaded', timeout=60000)
            task.add_log("✅ 页面加载成功", "success")
            
            return True
            
        except Exception as e:
            task.add_log(f"❌ 导航失败: {str(e)}", "error")
            return False
    
    async def configure_product(self, task: Task, url_analysis: dict = None) -> bool:
        """配置产品选项 - 基于apple_automator.py，跳过尺寸/颜色/内存，只配置必要选项"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log("🔧 开始配置产品选项（跳过尺寸/颜色/内存）...", "info")

            # 等待页面加载完成
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            # 1. 配置Apple Trade In - 必须选择 "No trade in"
            task.add_log("🔄 正在选择Apple Trade In: No trade in", "info")
            success = await self._apple_select_trade_in(page, "No trade in", task)
            if not success:
                task.add_log("❌ Apple Trade In选择失败", "error")
                return False
            task.add_log("✅ Apple Trade In选择完成", "success")
            await page.wait_for_timeout(1000)

            # 2. 配置Payment - 必须选择 "Buy"
            task.add_log("💳 正在选择Payment: Buy", "info")
            success = await self._apple_select_payment(page, "Buy", task)
            if not success:
                task.add_log("❌ Payment选择失败", "error")
                return False
            task.add_log("✅ Payment选择完成", "success")
            await page.wait_for_timeout(1000)

            # 3. 配置AppleCare+ Coverage - 必须选择 "No AppleCare+ Coverage"
            task.add_log("🛡️ 正在选择AppleCare+ Coverage: No AppleCare+ Coverage", "info")
            success = await self._apple_select_applecare(page, "No AppleCare+ Coverage", task)
            if not success:
                task.add_log("❌ AppleCare+ Coverage选择失败", "error")
                return False
            task.add_log("✅ AppleCare+ Coverage选择完成", "success")
            await page.wait_for_timeout(1000)

            task.add_log("🎉 产品配置完成", "success")
            return True
            
        except Exception as e:
            task.add_log(f"❌ 产品配置失败: {str(e)}", "error")
            return False
    
    async def add_to_bag(self, task: Task) -> bool:
        """添加到购物袋 - 基于apple_automator.py的精确实现"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log("🛒 正在将商品添加到购物袋...", "info")

            # 等待页面稳定（基于apple_automator.py）
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)

            # 重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        task.add_log(f"第{attempt+1}次尝试添加到购物袋", "info")
                        await page.wait_for_timeout(2000)

                    await self._find_and_click_add_to_bag(page, task)
                    task.add_log("✅ 商品已成功添加到购物袋", "success")

                    # 🚀 关键修复：添加到购物袋后，立即进入结账流程
                    task.add_log("🛒 开始进入结账流程...", "info")
                    await self.checkout(task)

                    return True

                except Exception as e:
                    task.add_log(f"第{attempt+1}次添加到购物袋失败: {e}", "warning")
                    if attempt == max_retries - 1:
                        task.add_log("❌ 无法添加商品到购物袋", "error")
                        return False

            return False

        except Exception as e:
            task.add_log(f"❌ 添加到购物袋失败: {str(e)}", "error")
            return False

    async def _find_and_click_add_to_bag(self, page: Page, task: Task):
        """查找并点击Add to Bag按钮 - 基于apple_automator.py"""
        # 滚动到页面底部寻找按钮
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

        # 尝试多种Add to Bag按钮选择器（来自apple_automator.py）
        selectors = [
            # 最常见的选择器
            'button[data-autom*="add-to-cart"]',
            'button[data-autom*="addToCart"]',
            '[data-autom="add-to-cart"]',

            # 文本匹配
            'button:has-text("Add to Bag")',
            'button:has-text("Add to Cart")',
            'button:has-text("添加到购物袋")',

            # 通用按钮选择器
            '.as-buttongroup-item button',
            'button[aria-label*="Add"]',
            'button[aria-label*="add"]',

            # 更广泛的搜索
            'button:has-text("Add")',
            '[role="button"]:has-text("Add to Bag")',
        ]

        for selector in selectors:
            try:
                task.add_log(f"尝试Add to Bag选择器: {selector}", "info")

                element = page.locator(selector).first

                # 等待元素可见 - 🚀 增加超时时间
                await element.wait_for(state='visible', timeout=20000)

                # 滚动到元素位置
                await element.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)

                # 确保元素可点击
                await element.wait_for(state='attached', timeout=5000)

                # 点击按钮
                await element.click()

                # 验证点击是否成功（等待页面变化或弹窗出现）
                await page.wait_for_timeout(2000)

                task.add_log(f"✅ 成功使用选择器点击Add to Bag: {selector}", "success")
                return

            except Exception as e:
                task.add_log(f"选择器 {selector} 失败: {e}", "warning")
                continue

        # 如果所有选择器都失败，尝试最后的备用策略
        task.add_log("尝试备用策略...", "info")
        await self._try_fallback_add_to_bag(page, task)

    async def _try_fallback_add_to_bag(self, page: Page, task: Task):
        """备用的Add to Bag策略 - 基于apple_automator.py"""
        # 策略1: 查找所有按钮，筛选包含"Add"的
        all_buttons = page.locator('button')
        button_count = await all_buttons.count()

        for i in range(button_count):
            try:
                button = all_buttons.nth(i)
                text = await button.inner_text()

                if any(keyword in text.lower() for keyword in ['add to bag', 'add to cart', 'add']):
                    task.add_log(f"找到可能的Add按钮: {text}", "info")
                    await button.scroll_into_view_if_needed()
                    await button.click()
                    task.add_log(f"✅ 使用备用策略成功点击: {text}", "success")
                    return

            except Exception as e:
                task.add_log(f"备用策略按钮 {i} 失败: {e}", "warning")
                continue

        raise Exception("所有Add to Bag策略都失败了")
    
    async def checkout(self, task: Task) -> bool:
        """结账流程 - 基于apple_automator.py的_review_bag_and_checkout"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log("💳 正在进入购物袋页面...", "info")

            # 等待页面稳定
            await page.wait_for_timeout(3000)

            # 多种Review Bag按钮选择策略（来自apple_automator.py）
            review_bag_strategies = [
                # 策略1: 原始选择器
                lambda: page.get_by_role('button', name='Review Bag'),
                # 策略2: 不同的文本变体
                lambda: page.get_by_role('button', name='Review bag'),
                lambda: page.get_by_role('button', name='View Bag'),
                lambda: page.get_by_role('button', name='Go to Bag'),
                # 策略3: 通过文本内容查找
                lambda: page.locator('button:has-text("Review Bag")'),
                lambda: page.locator('button:has-text("Review bag")'),
                lambda: page.locator('button:has-text("View Bag")'),
                lambda: page.locator('button:has-text("Go to Bag")'),
                # 策略4: 通过data属性
                lambda: page.locator('[data-autom*="bag"], [data-autom*="review"]'),
                # 策略5: 通过类名或ID
                lambda: page.locator('.review-bag, .view-bag, #reviewBag, #viewBag'),
            ]

            review_bag_success = False
            for i, strategy in enumerate(review_bag_strategies, 1):
                try:
                    task.add_log(f"尝试Review Bag策略 {i}", "info")
                    review_bag_button = strategy()

                    # 检查按钮是否存在
                    button_count = await review_bag_button.count()
                    if button_count == 0:
                        task.add_log(f"策略 {i}: 按钮不存在", "warning")
                        continue

                    # 检查按钮是否可见
                    is_visible = await review_bag_button.is_visible()
                    if not is_visible:
                        task.add_log(f"策略 {i}: 按钮存在但不可见，尝试滚动到视图", "info")
                        await review_bag_button.scroll_into_view_if_needed()
                        await page.wait_for_timeout(1000)
                        is_visible = await review_bag_button.is_visible()

                    if not is_visible:
                        task.add_log(f"策略 {i}: 按钮仍然不可见", "warning")
                        continue

                    # 检查按钮是否可点击
                    is_enabled = await review_bag_button.is_enabled()
                    if not is_enabled:
                        task.add_log(f"策略 {i}: 按钮不可点击", "warning")
                        continue

                    # 尝试点击
                    await review_bag_button.click()
                    task.add_log(f"✅ 成功点击Review Bag按钮 (策略{i})", "success")
                    review_bag_success = True
                    break

                except Exception as e:
                    task.add_log(f"Review Bag策略 {i} 失败: {e}", "warning")
                    continue

            if not review_bag_success:
                # 尝试备用策略
                task.add_log("尝试备用Review Bag策略...", "info")
                await self._try_fallback_review_bag(page, task)

            # 等待进入购物袋页面 - 🚀 增加超时时间应对网络延迟
            try:
                await page.wait_for_function(
                    "document.title.includes('Bag') || document.title.includes('Cart') || window.location.href.includes('bag') || window.location.href.includes('cart')",
                    timeout=30000  # 增加到30秒
                )
                task.add_log(f"✅ 已成功进入购物袋页面，标题: {await page.title()}", "success")

                # 智能处理Checkout按钮
                await self._handle_checkout_button(page, task)

                # 关键：等待页面导航完成后再处理登录
                await page.wait_for_load_state('domcontentloaded', timeout=20000)
                await page.wait_for_timeout(3000)
                task.add_log("✅ 页面导航完成，开始处理登录...", "info")

                # 等待并处理登录
                await self._handle_apple_login(page, task)

                return True

            except Exception as e:
                task.add_log(f"❌ 进入或处理购物袋页面时超时: {e}", "error")
                return False

        except Exception as e:
            task.add_log(f"❌ 结账失败: {str(e)}", "error")
            return False

    async def _try_fallback_review_bag(self, page: Page, task: Task):
        """备用的Review Bag策略 - 基于apple_automator.py"""
        # 查找所有按钮和链接，筛选包含相关关键词的
        all_elements = await page.locator('button, a, [role="button"]').all()

        for element in all_elements:
            try:
                text = await element.inner_text()
                text_lower = text.lower().strip()

                # 检查是否包含相关关键词
                if any(keyword in text_lower for keyword in [
                    'review bag', 'view bag', 'go to bag', 'checkout',
                    'bag', 'cart', 'continue', 'proceed'
                ]):
                    task.add_log(f"找到可能的Review Bag按钮: {text}", "info")

                    # 检查元素是否可见和可点击
                    if await element.is_visible() and await element.is_enabled():
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"✅ 使用备用策略成功点击: {text}", "success")
                        return

            except Exception as e:
                task.add_log(f"备用策略元素检查失败: {e}", "warning")
                continue

        # 如果还是找不到，尝试直接导航到购物袋页面
        task.add_log("⚠️ 无法找到Review Bag按钮，尝试直接导航到购物袋页面...", "warning")
        current_url = page.url

        # 构造购物袋URL
        if 'apple.com' in current_url:
            if '/uk/' in current_url:
                bag_url = 'https://www.apple.com/uk/shop/bag'
            elif '/us/' in current_url:
                bag_url = 'https://www.apple.com/us/shop/bag'
            else:
                bag_url = 'https://www.apple.com/shop/bag'

            task.add_log(f"直接导航到购物袋页面: {bag_url}", "info")
            await page.goto(bag_url)
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            return

        raise Exception("所有Review Bag策略都失败了")

    async def _handle_checkout_button(self, page: Page, task: Task):
        """智能处理Checkout按钮 - 基于apple_automator.py"""
        task.add_log("🔍 智能检测和处理Checkout按钮...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(3000)

        # 首先检查购物车是否有商品
        await self._verify_cart_has_items(page, task)

        # 尝试多种Checkout按钮选择策略
        checkout_strategies = [
            # 策略1: 原始选择器
            lambda: page.locator('[data-autom="checkout"]').first,
            # 策略2: 通过文本匹配
            lambda: page.get_by_role('button', name='Check Out'),
            # 策略3: 通过包含文本的按钮
            lambda: page.locator('button:has-text("Check Out")'),
            # 策略4: 通过类名
            lambda: page.locator('.checkout-button, .checkout-btn'),
            # 策略5: 通过ID
            lambda: page.locator('#checkout, #checkoutButton'),
            # 策略6: 更宽泛的选择器
            lambda: page.locator('button[class*="checkout"]'),
        ]

        checkout_success = False
        for i, strategy in enumerate(checkout_strategies, 1):
            try:
                task.add_log(f"尝试Checkout按钮策略 {i}", "info")
                checkout_button = strategy()

                # 检查按钮是否存在
                button_count = await checkout_button.count()
                if button_count == 0:
                    task.add_log(f"策略 {i}: 按钮不存在", "warning")
                    continue

                # 检查按钮是否可见
                is_visible = await checkout_button.is_visible()
                if not is_visible:
                    task.add_log(f"策略 {i}: 按钮存在但不可见，尝试滚动到视图", "info")
                    await checkout_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    is_visible = await checkout_button.is_visible()

                if not is_visible:
                    task.add_log(f"策略 {i}: 按钮仍然不可见", "warning")
                    continue

                # 检查按钮是否可点击
                is_enabled = await checkout_button.is_enabled()
                if not is_enabled:
                    task.add_log(f"策略 {i}: 按钮不可点击", "warning")
                    continue

                # 尝试点击
                await checkout_button.click()
                task.add_log(f"✅ 成功点击Checkout按钮 (策略{i})", "success")
                checkout_success = True
                break

            except Exception as e:
                task.add_log(f"Checkout按钮策略 {i} 失败: {e}", "warning")
                continue

        if not checkout_success:
            task.add_log("❌ 所有Checkout按钮策略都失败了，可能购物车为空或页面结构已变化", "error")
            raise Exception("无法找到或点击Checkout按钮")

        task.add_log("✅ 成功点击'Check Out'按钮，正在前往结账页面", "success")

    async def _verify_cart_has_items(self, page: Page, task: Task):
        """验证购物车是否有商品 - 基于apple_automator.py"""
        task.add_log("🔍 验证购物车商品...", "info")

        # 检查购物车商品数量
        item_selectors = [
            '.bag-item',
            '.cart-item',
            '[data-autom*="item"]',
            '.product-item',
            '.checkout-item'
        ]

        total_items = 0
        for selector in item_selectors:
            try:
                items = await page.locator(selector).count()
                if items > 0:
                    total_items = items
                    task.add_log(f"✅ 购物车中有 {items} 个商品", "success")
                    break
            except:
                continue

        if total_items == 0:
            task.add_log("⚠️ 购物车可能为空，这可能是Checkout按钮隐藏的原因", "warning")
            # 尝试查找"购物车为空"的提示
            empty_indicators = [
                ':has-text("empty")',
                ':has-text("Empty")',
                ':has-text("no items")',
                ':has-text("No items")'
            ]

            for indicator in empty_indicators:
                try:
                    empty_element = page.locator(indicator).first
                    if await empty_element.is_visible():
                        raise Exception("购物车为空，无法进行结账")
                except:
                    continue

    async def _handle_apple_login(self, page: Page, task: Task):
        """处理Apple ID登录 - 基于apple_automator.py的完整实现"""
        task.add_log("🔐 开始智能检测登录页面...", "info")

        # 获取登录配置 - 从account_config中获取
        account_config = task.config.account_config
        if not account_config:
            task.add_log("⚠️ 未配置账号信息，请检查任务配置", "error")
            return

        task.add_log(f"🔍 调试信息 - account_config: {account_config}", "info")

        email = account_config.email
        password = account_config.password
        phone_number = account_config.phone_number

        task.add_log(f"🔍 调试信息 - email: '{email}', password: '{password}', phone_number: '{phone_number}'", "info")

        if not email or not password:
            task.add_log("⚠️ 账号信息不完整（缺少邮箱或密码），请检查账号配置", "error")
            raise Exception("账号信息不完整：缺少邮箱或密码")

        task.add_log(f"使用账户: {email}", "info")
        task.add_log(f"电话号码: {phone_number}", "info")

        # SOTA方法：智能等待页面稳定
        await self._wait_for_page_stability(page, task)

        # 检测页面状态
        page_state = await self._detect_page_state(page)
        task.add_log(f"检测到页面状态: {page_state}", "info")

        if page_state == "already_logged_in":
            task.add_log("✅ 检测到已登录状态，跳过登录流程", "success")
            return
        elif page_state == "checkout_page":
            task.add_log("✅ 已在结账页面，继续后续流程", "success")
            await self._continue_checkout_flow(page, task, phone_number)
            return
        elif page_state == "product_config_page":
            task.add_log("⚠️ 检测到产品配置页面，但这里应该是登录处理阶段", "warning")
            task.add_log("这可能表示前面的checkout流程没有正确执行", "warning")
            # 不在这里处理产品配置页面，让调用方处理
            raise Exception("在登录阶段检测到产品配置页面，流程异常")

        # 增强的重试机制：最多尝试5次，针对高并发场景优化
        max_retries = 5
        for attempt in range(max_retries):
            try:
                task.add_log(f"登录尝试 {attempt + 1}/{max_retries}", "info")

                login_attempt_result = await self._attempt_smart_login(page, task, email, password, phone_number)

                # 登录尝试完成后，等待页面稳定并检测状态
                await page.wait_for_timeout(5000)  # 增加等待时间，确保页面完全加载
                current_url = page.url
                page_title = await page.title()

                task.add_log(f"登录尝试后当前URL: {current_url}", "info")
                task.add_log(f"登录尝试后页面标题: {page_title}", "info")

                # 更宽松的登录成功检测 - 优先检查URL
                login_success_indicators = [
                    'checkout', 'fulfillment', 'billing', 'payment', 'shipping',
                    'secure8.store.apple.com', 'store.apple.com/uk/shop/checkout'
                ]

                # 检查URL是否包含登录成功的指示器
                url_indicates_success = any(indicator in current_url.lower() for indicator in login_success_indicators)

                # 检查页面标题是否包含结账相关信息
                title_indicates_success = any(indicator in page_title.lower() for indicator in ['checkout', 'bag', 'cart', 'billing', 'payment'])

                # 如果URL或标题表明已经在结账流程中，认为登录成功
                if url_indicates_success or title_indicates_success:
                    task.add_log("✅ 登录成功，已进入结账流程", "success")
                    return
                elif login_attempt_result:
                    # 如果登录方法返回成功，但URL不明确，也认为成功
                    task.add_log("✅ 登录方法执行成功", "success")
                    return
                else:
                    # 只有在明确失败的情况下才抛出异常
                    raise Exception(f"登录失败，当前页面: {current_url}")

            except Exception as e:
                error_msg = str(e)
                task.add_log(f"第{attempt + 1}次登录失败: {error_msg}", "warning")

                # 检查是否是安全相关错误
                is_security_error = await self._is_security_related_error(page, error_msg)

                if attempt < max_retries - 1:
                    # 根据错误类型调整等待时间
                    if is_security_error:
                        # 安全错误需要更长的等待时间
                        wait_time = 5000 + (attempt * 3000)  # 5秒到14秒递增
                        task.add_log(f"检测到安全验证错误，等待 {wait_time/1000} 秒后重试...", "warning")
                    else:
                        # 普通错误较短等待时间
                        wait_time = 2000 + (attempt * 1000)  # 2秒到5秒递增
                        task.add_log(f"等待 {wait_time/1000} 秒后重试...", "info")

                    await page.wait_for_timeout(wait_time)

                    # 重新检测页面状态
                    page_state = await self._detect_page_state(page)
                    if page_state in ["already_logged_in", "checkout_page"]:
                        task.add_log("重试过程中检测到登录成功", "success")
                        await self._continue_checkout_flow(page, task, phone_number)
                        return
                else:
                    task.add_log("所有登录尝试都失败了", "error")
                    raise Exception(f"登录重试{max_retries}次后仍然失败: {error_msg}")

    async def _wait_for_page_stability(self, page: Page, task: Task):
        """SOTA方法：等待页面完全稳定 - 基于apple_automator.py"""
        task.add_log("⏳ 等待页面稳定...", "info")

        # 等待网络空闲 - 🚀 增加超时时间应对网络延迟
        try:
            await page.wait_for_load_state('networkidle', timeout=20000)
        except:
            await page.wait_for_load_state('domcontentloaded', timeout=20000)

        # 等待JavaScript执行完成
        await page.wait_for_function(
            "document.readyState === 'complete'",
            timeout=20000
        )

        # 额外等待确保动态内容加载
        await page.wait_for_timeout(2000)
        task.add_log("✅ 页面已稳定", "success")



    async def _is_security_related_error(self, page: Page, error_msg: str) -> bool:
        """判断是否是安全相关错误"""
        security_keywords = [
            "无法识别",
            "can't verify",
            "verification failed",
            "验证失败",
            "too many attempts",
            "暂时锁定",
            "temporarily locked",
            "请稍后再试",
            "try again later",
            "security",
            "安全"
        ]

        error_msg_lower = error_msg.lower()
        for keyword in security_keywords:
            if keyword.lower() in error_msg_lower:
                return True

        return False

    async def _attempt_smart_login(self, page: Page, task: Task, email: str, password: str, phone_number: str):
        """智能登录尝试，支持多种登录方式 - 基于apple_automator.py"""

        # 方法1: 检查iframe登录
        iframe_result = await self._try_iframe_login(page, task, email, password)
        if iframe_result:
            task.add_log("✅ iframe登录方法执行完成", "success")
            return True

        # 方法2: 检查直接登录表单
        direct_result = await self._try_direct_login(page, task, email, password)
        if direct_result:
            task.add_log("✅ 直接登录方法执行完成", "success")
            return True

        # 方法3: 检查是否需要点击登录链接
        signin_link_result = await self._try_signin_link(page, task)
        if signin_link_result:
            task.add_log("✅ 找到并点击了登录链接", "success")
            # 点击登录链接后等待页面加载，然后重新尝试登录
            await page.wait_for_timeout(3000)
            # 递归调用，但不返回结果，让上层重新检测
            return False

        # 如果所有方法都失败，返回False让上层处理
        task.add_log("⚠️ 所有登录方法都未找到可用的登录表单", "warning")
        return False

    async def _continue_checkout_flow(self, page: Page, task: Task, phone_number: str):
        """继续结账流程 - 基于apple_automator.py"""
        task.add_log("🔄 继续结账流程...", "info")

        # 登录后先点击Continue to Shipping Address按钮
        await self._continue_to_shipping_address(page, task)

        # 然后填写电话号码
        await self._fill_phone_number(page, task, phone_number)

        # 处理可能的地址确认卡片并继续到付款
        await self._handle_address_confirmation_and_continue(page, task)

    async def _detect_page_state(self, page: Page) -> str:
        """检测页面状态 - 修复版，避免误判产品配置页面"""
        current_url = page.url
        page_title = await page.title()

        # 🔍 首先检查是否在产品配置页面 - 但只在特定上下文中返回
        product_config_indicators = [
            'step=attach',
            'step=config',
            'step=select',
            'buy-iphone',
            'buy-ipad',
            'buy-mac',
            'purchaseOption=fullPrice'
        ]

        # 检查是否在产品配置页面，但不在登录检测中返回这个状态
        # 因为产品配置页面应该通过checkout流程处理，而不是登录流程
        is_product_config = any(indicator in current_url.lower() for indicator in product_config_indicators)
        if is_product_config and 'apple.com' in current_url and ('shop' in current_url or 'buy' in current_url):
            # 在产品配置页面时，检查是否有登录相关的元素
            # 如果没有，则返回unknown，让调用方决定如何处理
            pass  # 继续检查其他状态

        # 增强的结账页面检测 - 特别针对 secure8.store.apple.com 域名
        checkout_indicators = [
            'checkout',
            'billing',
            'payment',
            'fulfillment',  # 新增：针对 Fulfillment-init 等
            'shipping'
        ]

        # 检查是否已登录并在结账流程中
        if any(indicator in current_url.lower() for indicator in checkout_indicators):
            # 排除仍在登录页面的情况
            if 'signin' not in current_url.lower() and 'login' not in current_url.lower():
                # 特别检查 secure8.store.apple.com 域名
                if 'secure8.store.apple.com' in current_url or 'store.apple.com' in current_url:
                    return "checkout_page"
                # 其他Apple域名的结账页面
                elif 'apple.com' in current_url:
                    return "checkout_page"

        # 检查是否在登录页面 - 更严格的检测
        login_indicators = ['signin', 'login', 'auth', 'appleid']
        if any(indicator in current_url.lower() for indicator in login_indicators):
            return "login_page"

        # 检查页面内容 - 更精确的检测
        try:
            # 只有在明确的登录页面才检测登录表单
            if 'appleid' in current_url.lower() or 'idmsa' in current_url.lower():
                login_forms = await page.locator('iframe[src*="idmsa.apple.com"], iframe[src*="appleid.apple.com"]').count()
                if login_forms > 0:
                    return "login_page"

            # 检查是否有结账相关元素
            checkout_elements = await page.locator('[data-testid*="checkout"], [data-testid*="billing"], .checkout, .billing, [data-testid*="fulfillment"]').count()
            if checkout_elements > 0:
                return "checkout_page"

        except Exception as e:
            logger.debug(f"页面状态检测异常: {e}")

        # 如果是产品配置页面，返回unknown让调用方处理
        if is_product_config:
            return "unknown"

        return "unknown"



    async def _check_account_locked(self, page: Page, task: Task) -> bool:
        """检查账号是否被锁定（仅用于记录状态，不阻止登录流程）"""
        try:
            current_url = page.url
            page_title = await page.title()

            task.add_log(f"🔍 检查账号状态 - URL: {current_url}", "info")
            task.add_log(f"🔍 检查账号状态 - 标题: {page_title}", "info")

            # 等待页面稳定
            await page.wait_for_timeout(3000)

            # 检查页面内容中是否包含账号锁定的关键信息
            page_content = await page.content()

            # 检查多种可能的账号锁定提示
            lock_indicators = [
                "This Apple Account has been locked for security reasons",
                "You must unlock your account before signing in",
                "account has been locked",
                "account is locked",
                "security reasons",
                "unlock your account",
                "locked for security",
                "account locked",
                "temporarily locked",
                "suspended",
                "disabled"
            ]

            account_locked = False
            lock_message = ""

            # 记录页面内容的一部分用于调试
            content_preview = page_content[:1000] if len(page_content) > 1000 else page_content
            task.add_log(f"🔍 页面内容预览: {content_preview}", "debug")

            for indicator in lock_indicators:
                if indicator.lower() in page_content.lower():
                    account_locked = True
                    lock_message = indicator
                    task.add_log(f"🚨 检测到锁定关键词: {indicator}", "warning")
                    break

            # 也检查页面上是否有相关的错误元素
            if not account_locked:
                try:
                    # 检查常见的错误消息选择器
                    error_selectors = [
                        '.error-message',
                        '.alert-error',
                        '[role="alert"]',
                        '.notification-error',
                        '.security-message',
                        '.account-locked'
                    ]

                    for selector in error_selectors:
                        error_elements = await page.locator(selector).all()
                        for element in error_elements:
                            try:
                                error_text = await element.text_content()
                                if error_text and any(indicator.lower() in error_text.lower() for indicator in lock_indicators):
                                    account_locked = True
                                    lock_message = error_text.strip()
                                    break
                            except:
                                continue
                        if account_locked:
                            break

                except Exception as e:
                    logger.debug(f"检查错误元素失败: {e}")

            if account_locked:
                logger.warning(f"⚠️ 检测到账号可能被锁定: {lock_message}")
                await self._handle_account_locked(page, task, lock_message)
                return True

            return False

        except Exception as e:
            logger.error(f"检查账号锁定状态失败: {e}")
            return False

    async def _handle_account_locked(self, page: Page, task: Task, lock_message: str):
        """处理账号锁定问题（仅记录状态，不阻止流程）"""
        try:
            current_url = page.url
            page_title = await page.title()

            # 记录详细信息
            logger.warning(f"⚠️ 检测到账号可能存在安全问题")
            logger.warning(f"🔗 当前URL: {current_url}")
            logger.warning(f"📄 页面标题: {page_title}")
            logger.warning(f"💬 提示消息: {lock_message}")

            # 添加任务日志
            task.add_log("⚠️ 检测到账号可能存在安全问题", "warning")
            task.add_log(f"📄 页面标题: {page_title}", "info")
            task.add_log(f"🔗 当前URL: {current_url}", "info")
            task.add_log(f"💬 提示消息: {lock_message}", "info")
            task.add_log("📝 已记录账号状态，继续执行任务", "info")

            # 标记账号状态为异常
            if task.config.account_config:
                account_email = task.config.account_config.email
                await self._mark_account_as_abnormal(account_email, current_url, f"账号锁定: {lock_message}")
                task.add_log(f"🔴 账号 {account_email} 已标记为异常状态", "error")

            # 设置任务失败状态
            task.status = TaskStatus.FAILED
            task.error_message = f"账号已被锁定: {lock_message}"

            # 发送WebSocket更新到前端
            self._send_step_update(task, "account_locked", "failed", task.progress,
                                 f"账号锁定: {lock_message}")

            # 发送特殊的账号锁定事件到前端
            try:
                if hasattr(self, 'websocket_handler') and self.websocket_handler:
                    await self.websocket_handler.emit('account_security_issue', {
                        'task_id': task.id,
                        'account_email': task.config.account_config.email if task.config.account_config else None,
                        'current_url': current_url,
                        'page_title': page_title,
                        'lock_message': lock_message,
                        'timestamp': datetime.now().isoformat()
                    })
            except Exception as ws_error:
                logger.error(f"发送WebSocket事件失败: {ws_error}")

        except Exception as e:
            logger.error(f"处理账号锁定问题失败: {e}")
            task.add_log(f"❌ 处理账号锁定问题失败: {e}", "error")

    async def _handle_secure_checkout_issue(self, page: Page, task: Task):
        """处理Secure Checkout问题页面"""
        try:
            current_url = page.url
            page_title = await page.title()

            # 记录详细信息
            logger.error(f"🚨 遇到Secure Checkout问题页面")
            logger.error(f"🔗 当前URL: {current_url}")
            logger.error(f"📄 页面标题: {page_title}")

            # 添加任务日志
            task.add_log("🚨 检测到账号安全问题", "error")
            task.add_log(f"📄 页面标题: {page_title}", "error")
            task.add_log(f"🔗 当前URL: {current_url}", "error")
            task.add_log("⚠️ 账号可能需要额外验证或已被标记为异常", "warning")

            # 标记账号状态为异常
            if task.config.account_config:
                account_email = task.config.account_config.email
                await self._mark_account_as_abnormal(account_email, current_url, page_title)
                task.add_log(f"🔴 账号 {account_email} 已标记为异常状态", "error")

            # 设置任务失败状态
            task.status = TaskStatus.FAILED
            task.error_message = f"账号安全验证问题: {page_title}"

            # 发送WebSocket更新到前端
            self._send_step_update(task, "account_security_issue", "failed", task.progress,
                                 f"账号安全问题: {page_title}")

            # 发送特殊的账号异常事件到前端
            try:
                if hasattr(self, 'websocket_handler') and self.websocket_handler:
                    await self.websocket_handler.emit('account_security_issue', {
                        'task_id': task.id,
                        'account_email': task.config.account_config.email if task.config.account_config else None,
                        'current_url': current_url,
                        'page_title': page_title,
                        'timestamp': datetime.now().isoformat()
                    })
            except Exception as ws_error:
                logger.error(f"发送WebSocket事件失败: {ws_error}")

        except Exception as e:
            logger.error(f"处理Secure Checkout问题失败: {e}")
            task.add_log(f"❌ 处理账号安全问题失败: {e}", "error")

    async def _mark_account_as_abnormal(self, email: str, current_url: str, page_title: str):
        """标记账号为异常状态"""
        try:
            from models.database import DatabaseManager
            db_manager = DatabaseManager()

            # 更新账号状态为异常
            success = db_manager.update_account_status_by_email(email, "异常",
                f"Secure Checkout问题: {page_title} | URL: {current_url}")

            if success:
                logger.info(f"✅ 账号 {email} 状态已更新为异常")
            else:
                logger.warning(f"⚠️ 未找到账号 {email} 或更新失败")

        except Exception as e:
            logger.error(f"标记账号异常状态失败: {e}")

    async def _try_iframe_login(self, page: Page, task: Task, email: str, password: str) -> bool:
        """尝试iframe登录 - 基于apple_automator.py"""
        task.add_log("🔍 尝试iframe登录...", "info")

        # 检查多种iframe选择器
        iframe_selectors = [
            '#aid-auth-widget-iFrame',
            'iframe[name="aid-auth-widget"]',
            'iframe[title*="Sign In"]',
            'iframe[src*="idmsa.apple.com"]',
            'iframe[src*="appleid.apple.com"]'
        ]

        for selector in iframe_selectors:
            try:
                task.add_log(f"检查iframe选择器: {selector}", "info")
                iframe_element = page.locator(selector)

                if await iframe_element.count() == 0:
                    continue

                # 等待iframe可见
                await iframe_element.wait_for(state='visible', timeout=5000)

                # 获取frame对象
                frame = page.frame_locator(selector)

                # 等待iframe内容加载
                await self._wait_for_iframe_content(frame, task)

                # 执行登录
                await self._perform_iframe_login(frame, task, email, password)

                task.add_log("✅ iframe登录成功", "success")
                return True

            except Exception as e:
                task.add_log(f"iframe选择器 {selector} 失败: {e}", "warning")
                continue

        return False

    async def _wait_for_iframe_content(self, frame, task: Task):
        """等待iframe内容完全加载 - 基于apple_automator.py"""
        task.add_log("⏳ 等待iframe内容加载...", "info")

        # 等待iframe中的关键元素出现
        email_selectors = [
            'input[type="email"]',
            'input[name="accountName"]',
            '#account_name_text_field',
            '[placeholder*="email"]',
        ]

        for selector in email_selectors:
            try:
                await frame.locator(selector).first.wait_for(state='visible', timeout=5000)
                task.add_log(f"✅ iframe中找到邮箱输入框: {selector}", "success")
                return
            except:
                continue

        # 如果没有找到邮箱输入框，等待一般性内容
        await frame.locator('input, button').first.wait_for(state='visible', timeout=8000)

    async def _perform_iframe_login(self, frame, task: Task, email: str, password: str):
        """在iframe中执行登录 - 基于apple_automator.py"""
        task.add_log("📝 在iframe中执行登录...", "info")

        # 输入邮箱
        email_selectors = [
            'input[type="email"]',
            'input[name="accountName"]',
            '#account_name_text_field',
            '[placeholder*="email"]'
        ]

        email_input = None
        for selector in email_selectors:
            try:
                temp_input = frame.locator(selector).first
                await temp_input.wait_for(state='visible', timeout=3000)
                email_input = temp_input
                task.add_log(f"✅ 找到邮箱输入框: {selector}", "success")
                break
            except:
                continue

        if not email_input:
            raise Exception("无法找到邮箱输入框")

        await email_input.fill(email)
        task.add_log("✅ 邮箱已输入", "success")

        # 点击继续按钮或按Enter
        try:
            continue_btn = frame.locator('button[type="submit"], button:has-text("Continue")').first
            await continue_btn.click()
            task.add_log("✅ 已点击继续按钮", "success")
        except:
            await email_input.press('Enter')
            task.add_log("✅ 已按Enter键", "success")

        # 等待密码输入框出现
        await frame.locator('input[type="password"]').first.wait_for(state='visible', timeout=10000)

        # 输入密码
        password_input = frame.locator('input[type="password"]').first
        await password_input.fill(password)
        task.add_log("✅ 密码已输入", "success")

        # 提交密码
        try:
            submit_btn = frame.locator('button[type="submit"], button:has-text("Sign In")').first
            await submit_btn.click()
            task.add_log("✅ 已点击登录按钮", "success")
        except:
            await password_input.press('Enter')
            task.add_log("✅ 已按Enter键提交", "success")

        # 等待登录完成
        await page.wait_for_load_state('domcontentloaded', timeout=15000)

        # 等待页面稳定
        await page.wait_for_timeout(2000)

        task.add_log("✅ iframe登录流程完成", "success")

    async def _try_direct_login(self, page: Page, task: Task, email: str, password: str) -> bool:
        """尝试直接登录（非iframe）- 基于apple_automator.py"""
        task.add_log("🔍 尝试直接登录...", "info")

        try:
            # 查找邮箱输入框
            email_input = page.locator('input[type="email"], input[name="accountName"]').first
            if await email_input.count() == 0:
                return False

            await email_input.wait_for(state='visible', timeout=5000)
            await email_input.fill(email)
            task.add_log("✅ 邮箱已输入", "success")

            # 继续到密码
            try:
                continue_btn = page.locator('button[type="submit"], button:has-text("Continue")').first
                await continue_btn.click()
                await page.wait_for_timeout(2000)
                task.add_log("✅ 已点击继续按钮", "success")
            except:
                await email_input.press('Enter')
                await page.wait_for_timeout(2000)
                task.add_log("✅ 已按Enter键", "success")

            # 等待并输入密码
            password_input = page.locator('input[type="password"]').first
            await password_input.wait_for(state='visible', timeout=10000)
            await password_input.fill(password)
            task.add_log("✅ 密码已输入", "success")

            # 提交密码
            try:
                submit_btn = page.locator('button[type="submit"], button:has-text("Sign In")').first
                await submit_btn.click()
                task.add_log("✅ 已点击登录按钮", "success")
            except:
                await password_input.press('Enter')
                task.add_log("✅ 已按Enter键提交", "success")

            # 等待登录完成
            await page.wait_for_load_state('domcontentloaded', timeout=15000)

            # 等待页面稳定
            await page.wait_for_timeout(2000)

            task.add_log("✅ 直接登录流程完成", "success")
            return True

        except Exception as e:
            task.add_log(f"直接登录失败: {e}", "warning")
            return False

    async def _try_signin_link(self, page: Page, task: Task) -> bool:
        """尝试点击登录链接 - 基于apple_automator.py"""
        task.add_log("🔍 查找登录链接...", "info")

        signin_selectors = [
            'a:has-text("Sign In")',
            'a:has-text("Sign in")',
            'a:has-text("登录")',
            'button:has-text("Sign In")',
            'button:has-text("Sign in")',
            '[data-testid*="signin"]',
            '[data-autom*="signin"]'
        ]

        for selector in signin_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.wait_for(state='visible', timeout=3000)
                    if await element.is_visible():
                        await element.click()
                        task.add_log(f"✅ 已点击登录链接: {selector}", "success")
                        return True
            except:
                continue

        return False

    async def _continue_to_shipping_address(self, page: Page, task: Task):
        """点击Continue to Shipping Address按钮 - 基于apple_automator.py"""
        task.add_log("🚚 继续到配送地址...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(1000)  # 减少等待时间

        # 查找Continue按钮
        continue_selectors = [
            'button:has-text("Continue to Shipping Address")',
            'button:has-text("Continue")',
            'button[type="submit"]',
            '[data-testid*="continue"]',
            '[data-autom*="continue"]'
        ]

        for selector in continue_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.wait_for(state='visible', timeout=5000)
                    if await element.is_visible() and await element.is_enabled():
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"✅ 已点击Continue按钮: {selector}", "success")
                        await page.wait_for_timeout(3000)
                        return
            except:
                continue

        task.add_log("⚠️ 未找到Continue按钮，可能已在正确页面", "warning")

    async def _fill_phone_number(self, page: Page, task: Task, phone_number: str):
        """填写电话号码 - 基于apple_automator.py的完整实现"""
        task.add_log(f"📞 开始填写电话号码: {phone_number}", "info")

        # 等待页面稳定
        await page.wait_for_timeout(2000)

        # 尝试多种电话号码输入框选择器（基于apple_automator.py）
        phone_selectors = [
            'input[name="mobilePhone"]',
            'input[name="phoneNumber"]',
            'input[name="phone"]',
            'input[placeholder*="phone"]',
            'input[placeholder*="Phone"]',
            'input[placeholder*="mobile"]',
            'input[placeholder*="Mobile"]',
            'input[type="tel"]',
            '#mobilePhone',
            '#phoneNumber',
            '#phone',
            '[data-autom*="phone"]',
            '[data-autom*="mobile"]'
        ]

        phone_input = None
        for selector in phone_selectors:
            try:
                task.add_log(f"尝试电话号码选择器: {selector}", "info")
                temp_input = page.locator(selector).first
                await temp_input.wait_for(state='visible', timeout=3000)
                phone_input = temp_input
                task.add_log(f"✅ 找到电话号码输入框: {selector}", "success")
                break
            except:
                continue

        if phone_input is None:
            task.add_log("⚠️ 未找到电话号码输入框，可能不需要填写", "warning")
            return

        # SOTA方法：智能填写电话号码（基于apple_automator.py）
        try:
            # 检查元素类型和可编辑性
            tag_name = await phone_input.evaluate('el => el.tagName.toLowerCase()')
            is_input = tag_name in ['input', 'textarea']
            is_contenteditable = await phone_input.evaluate('el => el.contentEditable === "true"')

            if not is_input and not is_contenteditable:
                task.add_log(f"❌ 电话号码元素不可编辑: tagName={tag_name}", "error")
                raise Exception(f"电话号码输入框不是可编辑元素: {tag_name}")

            # 确保元素可交互
            await phone_input.wait_for(state='attached', timeout=5000)
            await phone_input.scroll_into_view_if_needed()

            # 清空并填写
            if is_input:
                await phone_input.clear()
                await phone_input.fill(phone_number)
            else:
                # 对于contenteditable元素
                await phone_input.click()
                await phone_input.evaluate('el => el.textContent = ""')
                await phone_input.type(phone_number)

            task.add_log("✅ 电话号码填写完成", "success")

            # 验证输入
            if is_input:
                input_value = await phone_input.input_value()
            else:
                input_value = await phone_input.text_content()

            if input_value.strip() != phone_number:
                task.add_log(f"⚠️ 电话号码验证失败，重试... 期望: {phone_number}, 实际: {input_value}", "warning")
                if is_input:
                    await phone_input.clear()
                    await page.wait_for_timeout(500)
                    await phone_input.fill(phone_number)
                else:
                    await phone_input.click()
                    await phone_input.evaluate('el => el.textContent = ""')
                    await phone_input.type(phone_number)

        except Exception as e:
            task.add_log(f"❌ 填写电话号码失败: {e}", "error")
            raise Exception(f"电话号码填写失败，无法继续: {e}")

        # 填写完电话号码后，点击Continue按钮
        await self._click_continue_after_phone(page, task)

    async def _click_continue_after_phone(self, page: Page, task: Task):
        """填写电话号码后点击Continue按钮 - 基于apple_automator.py"""
        task.add_log("📞 填写电话号码完成，点击Continue按钮...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(2000)

        # 尝试多种Continue按钮选择策略（基于apple_automator.py）
        continue_strategies = [
            # 策略1: 通过具体文本匹配
            lambda: page.get_by_role('button', name='Continue'),
            # 策略2: 通过包含Continue的按钮
            lambda: page.locator('button:has-text("Continue")'),
            # 策略3: 通过data-autom属性
            lambda: page.locator('[data-autom*="continue"]'),
            # 策略4: 通过类名和文本组合
            lambda: page.locator('button.form-button:has-text("Continue")'),
            # 策略5: 通过submit按钮
            lambda: page.locator('button[type="submit"]:has-text("Continue")'),
            # 策略6: 更宽泛的Continue按钮
            lambda: page.locator('button:has-text("Continue")').first,
            # 策略7: 通过表单中的Continue按钮
            lambda: page.locator('form button:has-text("Continue")').first,
        ]

        continue_success = False
        for i, strategy in enumerate(continue_strategies, 1):
            try:
                task.add_log(f"尝试Continue按钮选择策略 {i}", "info")
                continue_button = strategy()
                await continue_button.wait_for(state='visible', timeout=5000)
                await continue_button.scroll_into_view_if_needed()
                await continue_button.click()
                task.add_log(f"✅ 成功点击Continue按钮 (策略{i})", "success")
                continue_success = True
                break
            except Exception as e:
                task.add_log(f"Continue按钮选择策略 {i} 失败: {e}", "warning")
                continue

        if not continue_success:
            task.add_log("❌ 填写电话号码后无法找到Continue按钮", "error")
            raise Exception("填写电话号码后无法找到Continue按钮")

        # 等待页面响应
        await page.wait_for_load_state('domcontentloaded', timeout=15000)
        task.add_log("✅ 成功点击Continue按钮，等待页面响应...", "success")

    async def _handle_address_confirmation_and_continue(self, page: Page, task: Task):
        """处理地址确认卡片并继续到付款页面 - 基于apple_automator.py"""
        task.add_log("🏠 检查地址确认卡片并继续...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(2000)

        # 检查是否出现地址确认卡片
        await self._handle_address_confirmation(page, task)

        # 验证当前状态并继续到付款页面
        await self._verify_and_continue_to_payment(page, task)

    async def _handle_address_confirmation(self, page: Page, task: Task):
        """处理地址确认卡片，点击Use Existing Address - 基于apple_automator.py"""
        task.add_log("🔍 检查是否出现地址确认卡片...", "info")

        # 等待一下让卡片有时间出现
        await page.wait_for_timeout(2000)

        # 尝试多种"Use Existing Address"按钮选择策略（移除无效的策略）
        use_existing_strategies = [
            # 策略1: 通过包含文本的按钮（最有效的策略）
            lambda: page.locator('button:has-text("Use Existing Address")'),
            # 策略2: 通过包含Existing的按钮
            lambda: page.locator('button:has-text("Use Existing")'),
            # 策略3: 通过data-autom属性
            lambda: page.locator('[data-autom*="use-existing"], [data-autom*="existing-address"]'),
            # 策略4: 通过类名和文本组合
            lambda: page.locator('button.form-button:has-text("Use Existing")'),
            # 策略5: 通过对话框中的按钮
            lambda: page.locator('.modal button:has-text("Use Existing"), .dialog button:has-text("Use Existing")'),
            # 策略6: 通过卡片中的按钮
            lambda: page.locator('.card button:has-text("Use Existing"), .address-card button:has-text("Use Existing")'),
            # 策略7: 通过"Use this address!"按钮
            lambda: page.locator('button:has-text("Use this address!")'),
        ]

        address_confirmation_found = False
        for i, strategy in enumerate(use_existing_strategies, 1):
            try:
                task.add_log(f"尝试Use Existing Address按钮选择策略 {i}", "info")
                use_existing_button = strategy()
                await use_existing_button.wait_for(state='visible', timeout=3000)
                await use_existing_button.scroll_into_view_if_needed()
                await use_existing_button.click()
                task.add_log(f"✅ 成功点击'Use Existing Address'按钮 (策略{i})", "success")
                address_confirmation_found = True
                break
            except Exception as e:
                task.add_log(f"Use Existing Address按钮选择策略 {i} 失败: {e}", "warning")
                continue

        if not address_confirmation_found:
            task.add_log("ℹ️ 未发现地址确认卡片，继续执行...", "info")
        else:
            # 等待卡片消失
            await page.wait_for_timeout(2000)
            task.add_log("✅ 地址确认卡片处理完成", "success")

    async def _verify_and_continue_to_payment(self, page: Page, task: Task):
        """验证当前页面状态并智能继续到付款页面 - 基于apple_automator.py"""
        task.add_log("🔍 验证当前页面状态...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(2000)

        current_url = page.url
        page_title = await page.title()
        task.add_log(f"当前页面URL: {current_url}", "info")
        task.add_log(f"当前页面标题: {page_title}", "info")

        # 检查是否已经在付款页面（更精确的判断）
        payment_indicators = [
            'payment',
            'billing',
            'card'
        ]

        # 排除仍在配送阶段的URL
        shipping_exclusions = [
            'shipping-init',
            'shipping',
            'address'
        ]

        is_payment_page = (
            any(indicator in current_url.lower() or indicator in page_title.lower() for indicator in payment_indicators) and
            not any(exclusion in current_url.lower() for exclusion in shipping_exclusions)
        )

        if is_payment_page:
            task.add_log("✅ 已经在付款页面", "success")
            return

        # 检查是否还在配送地址页面，需要继续
        shipping_indicators = [
            'shipping',
            'address',
            'delivery'
        ]

        is_shipping_page = any(indicator in current_url.lower() or indicator in page_title.lower()
                              for indicator in shipping_indicators)

        if is_shipping_page:
            task.add_log("🚚 仍在配送地址页面，尝试继续到付款页面...", "info")
            await self._continue_to_payment(page, task)
        else:
            # 检查页面上是否有Continue to Payment按钮
            try:
                continue_payment_btn = page.locator('button:has-text("Continue to Payment"), button:has-text("Continue")').first
                await continue_payment_btn.wait_for(state='visible', timeout=5000)
                task.add_log("发现Continue按钮，点击继续...", "info")
                await self._continue_to_payment(page, task)
            except:
                task.add_log("⚠️ 无法确定当前页面状态，尝试通用Continue按钮...", "warning")
                # 尝试通用的Continue按钮
                await self._try_generic_continue_button(page, task)

    async def _try_generic_continue_button(self, page: Page, task: Task):
        """尝试通用的Continue按钮 - 基于apple_automator.py"""
        task.add_log("🔄 尝试通用Continue按钮...", "info")

        # 通用Continue按钮选择器
        generic_continue_selectors = [
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button[type="submit"]',
            'input[type="submit"]',
            '[data-autom*="continue"]',
            '[data-autom*="next"]',
            '.continue-button',
            '.next-button'
        ]

        for selector in generic_continue_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0:
                    await button.scroll_into_view_if_needed()
                    if await button.is_visible() and await button.is_enabled():
                        await button.click()
                        task.add_log(f"✅ 成功点击通用Continue按钮: {selector}", "success")
                        await page.wait_for_timeout(3000)
                        return
            except Exception as e:
                task.add_log(f"通用Continue按钮 {selector} 失败: {e}", "warning")
                continue

        task.add_log("❌ 未找到可用的Continue按钮", "error")
        # 截图用于调试
        await page.screenshot(path=f"no_continue_button_{task.id}.png")

    async def _continue_to_payment(self, page: Page, task: Task):
        """点击Continue to Payment按钮 - 直接使用有效的策略4"""
        task.add_log("🔄 点击Continue to Payment按钮...", "info")

        # 直接使用策略4（已验证有效）：通过data-autom属性
        try:
            continue_button = page.locator('[data-autom*="continue"], [data-autom*="payment"]')
            await continue_button.wait_for(state='visible', timeout=5000)
            await continue_button.scroll_into_view_if_needed()
            await continue_button.click()
            task.add_log("✅ 成功点击'Continue to Payment'按钮", "success")
        except Exception as e:
            task.add_log(f"❌ 无法找到Continue to Payment按钮: {e}", "error")
            raise Exception("无法找到Continue to Payment按钮")

        # 等待页面跳转
        await page.wait_for_timeout(3000)

        # 验证是否真的进入了付款页面
        await self._verify_payment_page_entry(page, task)

    async def _verify_payment_page_entry(self, page: Page, task: Task):
        """验证是否成功进入付款页面 - 基于apple_automator.py"""
        task.add_log("🔍 验证是否成功进入付款页面...", "info")

        # 验证是否真的进入了付款页面
        await page.wait_for_timeout(3000)
        current_url = page.url
        page_title = await page.title()

        # 更精确的付款页面判断
        payment_indicators = ['payment', 'billing', 'card']
        shipping_exclusions = ['shipping-init', 'shipping', 'address']

        is_payment_page = (
            any(indicator in current_url.lower() or indicator in page_title.lower() for indicator in payment_indicators) and
            not any(exclusion in current_url.lower() for exclusion in shipping_exclusions)
        )

        if is_payment_page:
            task.add_log("✅ 成功进入付款页面", "success")
            task.add_log("🎉 地址确认和页面跳转流程完成", "success")

            # 进入付款页面后，等待页面完全稳定，然后应用礼品卡
            task.add_log("⏳ 等待付款页面完全加载...", "info")
            await page.wait_for_timeout(3000)  # 减少等待时间

            # 应用礼品卡
            await self.apply_gift_card(task)
        else:
            task.add_log(f"⚠️ 仍未进入付款页面 - URL: {current_url}, 标题: {page_title}", "warning")
            task.add_log("🔄 尝试继续到付款页面...", "info")

            # 尝试继续到付款页面
            try:
                await self._try_generic_continue_button(page, task)
                # 再次验证
                await page.wait_for_timeout(3000)
                new_url = page.url
                new_title = await page.title()

                new_is_payment_page = (
                    any(indicator in new_url.lower() or indicator in new_title.lower() for indicator in payment_indicators) and
                    not any(exclusion in new_url.lower() for exclusion in shipping_exclusions)
                )

                if new_is_payment_page:
                    task.add_log("✅ 成功进入付款页面", "success")
                    await self.apply_gift_card(task)
                else:
                    task.add_log(f"❌ 仍无法进入付款页面 - URL: {new_url}", "error")
                    # 截图用于调试
                    await page.screenshot(path=f"payment_verification_failed_{task.id}.png")
            except Exception as e:
                task.add_log(f"❌ 尝试进入付款页面失败: {e}", "error")
                await page.screenshot(path=f"payment_verification_error_{task.id}.png")
    
    async def apply_gift_card(self, task: Task) -> bool:
        """礼品卡应用流程 - 重定向到阶段4方法"""
        return await self._execute_stage_4_gift_card(task)

    async def continue_with_gift_cards(self, task: Task, gift_cards: list) -> bool:
        """用户提交礼品卡后继续执行"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log(f"🎁 收到用户提交的 {len(gift_cards)} 张礼品卡，开始应用...", "info")

            # 应用每张礼品卡
            for i, gift_card in enumerate(gift_cards, 1):
                gift_card_number = gift_card.get('number', '')
                expected_status = gift_card.get('status', 'unknown')

                task.add_log(f"🎯 应用第 {i} 张礼品卡: {gift_card_number[:4]}**** (状态: {expected_status})", "info")

                try:
                    # 点击礼品卡链接
                    await self._sota_click_gift_card_link(page, task)

                    # 填写礼品卡号码
                    await self._sota_fill_gift_card_input(page, task, gift_card_number)

                    # 点击Apply按钮
                    await self._apply_gift_card_and_get_feedback(page, task)

                    task.add_log(f"✅ 第 {i} 张礼品卡应用完成", "success")

                    # 如果还有更多礼品卡，等待页面更新
                    if i < len(gift_cards):
                        await page.wait_for_timeout(2000)

                except Exception as e:
                    task.add_log(f"❌ 第 {i} 张礼品卡应用失败: {e}", "error")
                    continue

            task.add_log("🎉 所有礼品卡应用完成", "success")

            # 恢复任务状态为运行中
            task.status = TaskStatus.RUNNING

            return True

        except Exception as e:
            task.add_log(f"❌ 继续礼品卡应用失败: {e}", "error")
            return False

            # 获取前端传递的真实礼品卡配置（保留原有代码以防需要）
            gift_card_code = getattr(task.config, 'gift_card_code', None)
            gift_cards = getattr(task.config, 'gift_cards', None)

            # 写入专门的调试日志文件
            debug_log_path = f"debug_gift_card_{task.id}.log"
            with open(debug_log_path, 'w', encoding='utf-8') as debug_file:
                debug_file.write("=== 多张礼品卡调试信息 ===\n")
                debug_file.write(f"任务ID: {task.id}\n")
                debug_file.write(f"时间: {datetime.now()}\n\n")

                debug_file.write("1. task.config基本信息:\n")
                debug_file.write(f"   类型: {type(task.config)}\n")
                debug_file.write(f"   所有属性: {dir(task.config)}\n\n")

                debug_file.write("2. getattr方式获取:\n")
                debug_file.write(f"   gift_card_code: {gift_card_code}\n")
                debug_file.write(f"   gift_cards: {gift_cards}\n\n")

                debug_file.write("3. 直接访问属性:\n")
                try:
                    direct_gift_cards = task.config.gift_cards
                    direct_gift_card_code = task.config.gift_card_code
                    debug_file.write(f"   直接访问成功:\n")
                    debug_file.write(f"   gift_cards: {direct_gift_cards}\n")
                    debug_file.write(f"   gift_card_code: {direct_gift_card_code}\n")
                except AttributeError as e:
                    debug_file.write(f"   直接访问失败: {e}\n")

                debug_file.write("\n4. task.config完整内容:\n")
                try:
                    debug_file.write(f"   {vars(task.config)}\n")
                except Exception as e:
                    debug_file.write(f"   无法获取vars: {e}\n")

                debug_file.write("\n5. task完整内容:\n")
                try:
                    debug_file.write(f"   {vars(task)}\n")
                except Exception as e:
                    debug_file.write(f"   无法获取task vars: {e}\n")

            task.add_log(f"📝 调试信息已写入文件: {debug_log_path}", "info")
            task.add_log(f"🔍 调试 - gift_card_code: {gift_card_code}, gift_cards: {gift_cards}", "info")

            # 解析所有礼品卡
            cards_to_apply = []
            
            # 处理新格式的多张礼品卡
            if gift_cards and len(gift_cards) > 0:
                for i, card in enumerate(gift_cards):
                    if isinstance(card, dict):
                        card_number = card.get('number')
                        expected_status = card.get('expected_status', 'has_balance')
                        if card_number:
                            cards_to_apply.append({
                                'number': card_number,
                                'expected_status': expected_status,
                                'index': i + 1
                            })
                    elif isinstance(card, str) and card:
                        cards_to_apply.append({
                            'number': card,
                            'expected_status': 'has_balance',
                            'index': i + 1
                        })
            
            # 兼容旧格式的单张礼品卡
            elif gift_card_code:
                cards_to_apply.append({
                    'number': gift_card_code,
                    'expected_status': 'has_balance',
                    'index': 1
                })

            # 如果没有找到礼品卡配置，跳过礼品卡应用
            if not cards_to_apply:
                task.add_log("⚠️ 配置中未找到礼品卡号码，跳过礼品卡应用", "warning")
                self._send_step_update(task, "applying_gift_card", "completed", 100, "跳过礼品卡应用")
                return True

            task.add_log(f"🎁 准备应用 {len(cards_to_apply)} 张礼品卡", "info")
            self._send_step_update(task, "applying_gift_card", "progress", 10, f"准备应用{len(cards_to_apply)}张礼品卡")

            # SOTA方法2：等待页面完全稳定
            task.add_log("⏳ 等待结账页面完全稳定...", "info")
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            # 应用每张礼品卡
            successful_cards = 0
            failed_cards = 0
            
            for card_info in cards_to_apply:
                card_number = card_info['number']
                card_index = card_info['index']
                expected_status = card_info['expected_status']
                
                try:
                    task.add_log(f"🎁 开始应用第 {card_index} 张礼品卡: {card_number[:4]}**** (期望状态: {expected_status})", "info")
                    progress = 20 + (card_index - 1) * (60 / len(cards_to_apply))
                    self._send_step_update(task, "applying_gift_card", "progress", progress, f"应用第{card_index}张礼品卡")
                    
                    # 应用单张礼品卡
                    await self._apply_single_gift_card(page, task, card_number, card_index, len(cards_to_apply))
                    
                    successful_cards += 1
                    task.add_log(f"✅ 第 {card_index} 张礼品卡应用成功", "success")
                    
                    # 如果还有更多礼品卡需要应用，寻找"add another card"选项
                    if card_index < len(cards_to_apply):
                        task.add_log(f"🔄 准备添加下一张礼品卡 ({card_index + 1}/{len(cards_to_apply)})", "info")
                        await self._click_add_another_card(page, task)
                    
                except Exception as e:
                    failed_cards += 1
                    task.add_log(f"❌ 第 {card_index} 张礼品卡应用失败: {e}", "error")
                    
                    # 根据期望状态决定是否继续
                    if expected_status == "zero_balance" or expected_status == "error":
                        task.add_log(f"⚠️ 第 {card_index} 张礼品卡期望状态为 {expected_status}，继续处理下一张", "warning")
                    else:
                        # 如果是意外的错误，截图调试但继续处理下一张
                        try:
                            await page.screenshot(path=f"error_gift_card_{task.id}_card_{card_index}.png")
                        except:
                            pass
                        task.add_log(f"⚠️ 第 {card_index} 张礼品卡应用失败，继续处理下一张", "warning")

            # 总结礼品卡应用结果
            task.add_log(f"🎯 礼品卡应用完成: 成功 {successful_cards} 张，失败 {failed_cards} 张", "info")
            
            if successful_cards > 0:
                task.add_log("🎉 至少有一张礼品卡应用成功", "success")
                self._send_step_update(task, "applying_gift_card", "completed", 100, f"成功应用{successful_cards}张礼品卡")
                
                # 等待并检查最终结果
                await page.wait_for_timeout(3000)
                await self._check_multiple_gift_cards_result(page, task)
            else:
                task.add_log("❌ 所有礼品卡应用都失败了", "error")
                self._send_step_update(task, "applying_gift_card", "failed", message="所有礼品卡应用失败")

            return True

        except Exception as e:
            task.add_log(f"❌ 多张礼品卡应用流程失败: {e}", "error")
            self._send_step_update(task, "applying_gift_card", "failed", message=f"礼品卡应用失败: {str(e)}")
            
            # 截图调试
            try:
                await page.screenshot(path=f"error_multi_gift_card_{task.id}.png")
                page_content = await page.content()
                with open(f"debug_multi_gift_card_{task.id}.html", 'w', encoding='utf-8') as f:
                    f.write(page_content)
            except:
                pass

            # 即使失败也继续，让用户手动处理
            task.add_log("⚠️ 多张礼品卡应用失败，继续到最终步骤", "warning")
            return True

    async def _apply_single_gift_card(self, page: Page, task: Task, gift_card_number: str, card_index: int, total_cards: int):
        """应用单张礼品卡的完整流程 - 集成IP切换功能"""
        try:
            # 🔄 在应用礼品卡前切换IP - 核心防封功能
            task.add_log(f"🔄 第 {card_index} 张礼品卡：准备切换IP避免封禁...", "info")
            
            # 为此礼品卡切换到专用IP
            new_proxy = await self.ip_service.rotate_ip_for_gift_card(task.id, gift_card_number)
            
            if new_proxy:
                task.add_log(f"✅ 已切换到新IP: {new_proxy.host}:{new_proxy.port} ({new_proxy.country})", "success")
                
                # 重新创建浏览器上下文以使用新代理
                if await self._recreate_browser_context_with_proxy(task, new_proxy):
                    task.add_log("✅ 浏览器上下文已使用新代理重新创建", "success")
                else:
                    task.add_log("⚠️ 代理应用失败，使用原有连接继续", "warning")
            else:
                task.add_log("⚠️ IP切换失败，使用当前IP继续", "warning")
            
            # 原有的礼品卡应用流程
            # 对于第一张礼品卡，需要点击链接打开输入框
            if card_index == 1:
                task.add_log("🔗 步骤1: 点击'Enter your gift card number'链接...", "info")
                await self._sota_click_gift_card_link(page, task)
            else:
                task.add_log(f"🔗 第 {card_index} 张礼品卡: 礼品卡输入框应该已经可见", "info")

            task.add_log(f"📝 步骤2: 填写第 {card_index} 张礼品卡号码...", "info")
            await self._sota_fill_gift_card_input(page, task, gift_card_number)

            task.add_log(f"✅ 步骤3: 点击Apply按钮应用第 {card_index} 张礼品卡...", "info")
            await self._apply_gift_card_and_get_feedback(page, task, gift_card_number)

            task.add_log(f"🎉 第 {card_index} 张礼品卡应用流程完成", "success")

            # 等待页面响应
            await page.wait_for_timeout(2000)
            
        except Exception as e:
            task.add_log(f"❌ 第 {card_index} 张礼品卡应用流程失败: {e}", "error")
            
            # 如果礼品卡被拒绝，可能是IP被封，标记此IP
            if "blocked" in str(e).lower() or "rejected" in str(e).lower():
                current_proxy = self.ip_service.get_current_proxy()
                if current_proxy:
                    ip_address = f"{current_proxy.host}:{current_proxy.port}"
                    self.ip_service.mark_ip_blocked(ip_address, f"Gift card {gift_card_number[:4]}**** rejected")
                    task.add_log(f"🚫 IP {ip_address} 已标记为被封禁", "error")
            
            raise

    async def _recreate_browser_context_with_proxy(self, task: Task, proxy_info) -> bool:
        """使用新代理重新创建浏览器上下文"""
        try:
            # 获取当前页面的URL以便重新导航
            current_page = self.pages.get(task.id)
            if not current_page:
                task.add_log("❌ 无法找到当前页面", "error")
                return False
            
            current_url = current_page.url
            task.add_log(f"📍 当前页面URL: {current_url}", "info")
            
            # 关闭旧的上下文和页面
            old_context = self.contexts.get(task.id)
            if old_context:
                await old_context.close()
            
            # 获取Playwright代理配置
            proxy_config = self.ip_service.get_proxy_config_for_playwright()
            
            # 创建新的上下文（使用新代理）
            new_context = await self.browser.new_context(
                locale="en-GB",
                proxy=proxy_config
            )
            new_page = await new_context.new_page()
            
            # 更新存储的上下文和页面
            self.contexts[task.id] = new_context
            self.pages[task.id] = new_page
            
            # 重新导航到当前URL
            task.add_log("🔄 使用新代理重新加载页面...", "info")
            await new_page.goto(current_url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待页面稳定
            await new_page.wait_for_timeout(3000)
            
            task.add_log("✅ 浏览器上下文已成功重新创建", "success")
            return True
            
        except Exception as e:
            task.add_log(f"❌ 重新创建浏览器上下文失败: {str(e)}", "error")
            return False

    async def _click_add_another_card(self, page: Page, task: Task):
        """点击"Add Another Card"或类似的按钮来添加下一张礼品卡"""
        try:
            task.add_log("🔍 寻找'Add Another Card'选项...", "info")
            
            # 等待页面稳定
            await page.wait_for_timeout(2000)
            
            # Apple网站上可能的"添加另一张卡"选项
            add_card_selectors = [
                # 最常见的Apple官网样式
                'button:has-text("Add Another Card")',
                'a:has-text("Add Another Card")',
                'button:has-text("Add another card")',
                'a:has-text("Add another card")',
                
                # 可能的变体
                'button:has-text("Add Gift Card")',
                'a:has-text("Add Gift Card")',
                'button:has-text("Add another gift card")',
                'a:has-text("Add another gift card")',
                
                # 通过data属性查找
                '[data-autom*="add-gift-card"]',
                '[data-autom*="add-another-card"]',
                '[data-autom*="additional-gift-card"]',
                
                # 可能包含加号的按钮
                'button:has-text("+")',
                '[aria-label*="Add"]',
                '[aria-label*="add"]',
                
                # 通用的添加按钮
                'button:has-text("Add")',
                'a:has-text("Add")',
                
                # 如果是链接形式的
                'text="Enter another gift card number"',
                'text="Add another gift card number"',
                'text="Use another gift card"'
            ]
            
            for i, selector in enumerate(add_card_selectors, 1):
                try:
                    task.add_log(f"🔍 尝试Add Another Card选择器 {i}: {selector}", "info")
                    element = page.locator(selector).first
                    
                    count = await element.count()
                    if count == 0:
                        continue
                        
                    # 检查元素是否可见
                    is_visible = await element.is_visible()
                    if not is_visible:
                        task.add_log(f"  选择器 {i}: 元素存在但不可见", "warning")
                        continue
                    
                    # 检查元素是否可点击
                    is_enabled = await element.is_enabled()
                    if not is_enabled:
                        task.add_log(f"  选择器 {i}: 元素不可点击", "warning")
                        continue
                    
                    # 滚动到元素位置并点击
                    await element.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await element.click()
                    
                    task.add_log(f"✅ 成功点击'Add Another Card'按钮 (选择器{i})", "success")
                    
                    # 等待新的输入框出现
                    await page.wait_for_timeout(2000)
                    return
                    
                except Exception as e:
                    task.add_log(f"  选择器 {i} 失败: {e}", "warning")
                    continue
            
            # 如果没有找到"Add Another Card"按钮，可能页面已经有输入框了
            task.add_log("⚠️ 未找到'Add Another Card'按钮，检查是否已有可用输入框", "warning")
            
            # 检查是否已经有可用的礼品卡输入框
            gift_card_input_selectors = [
                'input[placeholder*="gift card"]',
                'input[placeholder*="Gift Card"]',
                'input[id*="giftCard"]',
                'input[data-autom*="gift-card"]'
            ]
            
            for selector in gift_card_input_selectors:
                try:
                    input_element = page.locator(selector).first
                    if await input_element.count() > 0 and await input_element.is_visible():
                        # 检查输入框是否为空（可以用于下一张卡）
                        input_value = await input_element.input_value()
                        if not input_value or input_value.strip() == '':
                            task.add_log("✅ 找到空的礼品卡输入框，可以直接使用", "success")
                            return
                except:
                    continue
            
            # 最后尝试：可能需要再次点击礼品卡链接
            task.add_log("🔄 尝试再次点击礼品卡链接来添加下一张卡", "info")
            try:
                await self._sota_click_gift_card_link(page, task)
                return
            except Exception as e:
                task.add_log(f"再次点击礼品卡链接失败: {e}", "warning")
            
            # 如果所有方法都失败，记录警告但不抛出异常
            task.add_log("⚠️ 无法找到添加下一张礼品卡的方法，可能需要手动处理", "warning")
            
        except Exception as e:
            task.add_log(f"❌ 点击'Add Another Card'失败: {e}", "error")
            # 不抛出异常，让流程继续

    async def _check_multiple_gift_cards_result(self, page: Page, task: Task):
        """检查多张礼品卡应用结果"""
        try:
            task.add_log("🔍 检查多张礼品卡应用结果...", "info")

            # 检查成功消息
            success_indicators = []
            success_selectors = [
                '.success',
                '.alert-success',
                '.notification-success',
                '.message-success',
                '.gift-card-success',
                'text="Gift card applied"',
                'text="Applied successfully"',
                'text="礼品卡已应用"',
                '[data-testid*="success"]'
            ]

            for selector in success_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        element = elements.nth(i)
                        if await element.is_visible():
                            success_text = await element.text_content()
                            if success_text and success_text.strip():
                                success_indicators.append(success_text.strip())
                except:
                    continue

            if success_indicators:
                task.add_log(f"✅ 发现成功指示器: {', '.join(success_indicators)}", "success")

            # 检查错误消息
            error_indicators = []
            error_selectors = [
                '.error',
                '.alert-error',
                '.notification-error',
                '.message-error',
                '.gift-card-error',
                'text="Invalid gift card"',
                'text="Gift card not found"',
                'text="礼品卡无效"',
                '[data-testid*="error"]'
            ]

            for selector in error_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        element = elements.nth(i)
                        if await element.is_visible():
                            error_text = await element.text_content()
                            if error_text and error_text.strip():
                                error_indicators.append(error_text.strip())
                except:
                    continue

            if error_indicators:
                task.add_log(f"❌ 发现错误指示器: {', '.join(error_indicators)}", "error")

            # 检查页面上的总价变化（多张礼品卡可能导致多次价格调整）
            total_prices = []
            total_selectors = [
                '.total-price',
                '.order-total',
                '.grand-total',
                '[data-testid*="total"]',
                '[data-testid*="price"]'
            ]

            for selector in total_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        element = elements.nth(i)
                        if await element.is_visible():
                            total_text = await element.text_content()
                            if total_text and ('$' in total_text or '￥' in total_text or '£' in total_text):
                                total_prices.append(total_text.strip())
                except:
                    continue

            if total_prices:
                unique_prices = list(set(total_prices))
                task.add_log(f"💰 当前订单价格信息: {', '.join(unique_prices)}", "info")

            # 检查已应用的礼品卡列表
            applied_cards = []
            applied_card_selectors = [
                '.applied-gift-card',
                '.gift-card-applied',
                '[data-testid*="applied-gift-card"]',
                '.payment-method[data-type="gift-card"]'
            ]

            for selector in applied_card_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        element = elements.nth(i)
                        if await element.is_visible():
                            card_text = await element.text_content()
                            if card_text and card_text.strip():
                                applied_cards.append(card_text.strip())
                except:
                    continue

            if applied_cards:
                task.add_log(f"🎁 检测到已应用的礼品卡: {len(applied_cards)} 张", "info")
                for i, card_info in enumerate(applied_cards, 1):
                    task.add_log(f"  第{i}张: {card_info[:50]}...", "info")
            else:
                task.add_log("ℹ️ 未检测到明确的已应用礼品卡列表", "info")

            # 总结检查结果
            if success_indicators and not error_indicators:
                task.add_log("🎉 多张礼品卡应用看起来成功了", "success")
            elif error_indicators and not success_indicators:
                task.add_log("❌ 多张礼品卡应用看起来失败了", "error")
            elif success_indicators and error_indicators:
                task.add_log("⚠️ 礼品卡应用结果混合：部分成功，部分失败", "warning")
            else:
                task.add_log("ℹ️ 礼品卡应用状态不明确，请手动检查页面", "info")

        except Exception as e:
            task.add_log(f"⚠️ 检查多张礼品卡应用结果时出错: {e}", "warning")

    async def _sota_click_gift_card_link(self, page: Page, task: Task):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await page.wait_for_timeout(1000)

        # 基于实际测试结果的有效选择器
        effective_selectors = [
            # 最有效的选择器（实际测试成功）
            'button[data-autom="enter-giftcard-number"]',  # 从错误日志中发现的实际按钮
            '[data-autom*="gift"]',
            # 备用选择器
            'text="Enter your gift card number"',
            'a:has-text("Enter your gift card number")',
            'text="Do you have an Apple Gift Card?"',
            'button:has-text("gift card")',
            'a:has-text("gift card")'
        ]

        link_found = False
        for i, selector in enumerate(effective_selectors, 1):
            try:
                task.add_log(f"🔍 尝试选择器 {i}: {selector}", "info")
                gift_card_link = page.locator(selector).first

                count = await gift_card_link.count()
                task.add_log(f"  找到 {count} 个匹配元素", "info")

                if count > 0:
                    await gift_card_link.wait_for(state='visible', timeout=3000)
                    await gift_card_link.scroll_into_view_if_needed()
                    await gift_card_link.click()
                    task.add_log(f"✅ 成功点击礼品卡链接 (选择器{i})", "success")
                    link_found = True
                    break

            except Exception as e:
                task.add_log(f"  选择器 {i} 失败: {e}", "warning")
                continue

        if not link_found:
            task.add_log("❌ 未找到礼品卡链接，开始详细调试...", "error")

            # 调试：搜索页面上所有包含gift的文本
            try:
                gift_elements = page.locator('*:has-text("gift"), *:has-text("Gift")')
                count = await gift_elements.count()
                task.add_log(f"📊 页面上共有 {count} 个包含'gift'的元素", "info")

                for i in range(min(count, 5)):
                    try:
                        element = gift_elements.nth(i)
                        text = await element.text_content()
                        tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                        task.add_log(f"  {i+1}. <{tag_name}>: {text[:50]}...", "info")
                    except:
                        pass
            except:
                pass

            # 截图调试
            await page.screenshot(path=f"no_gift_card_link_{task.id}.png")
            raise Exception("未找到礼品卡链接")

        # 等待页面响应
        await page.wait_for_timeout(2000)
        task.add_log("✅ 礼品卡链接点击完成，等待输入框出现", "success")

    async def _sota_fill_gift_card_input(self, page: Page, task: Task, gift_card_number: str):
        """SOTA方法：填写礼品卡号码 - 严格基于apple_automator.py"""
        task.add_log(f"📝 SOTA方法：填写礼品卡号码 {gift_card_number[:4]}****", "info")

        # 等待输入框出现（点击链接后）
        await page.wait_for_timeout(3000)

        # 基于实际测试结果的有效选择器
        gift_card_selectors = [
            # 最有效的选择器（从错误日志中发现）
            'input[id="checkout.billing.billingOptions.selectedBillingOptions.giftCard.giftCardInput.giftCard"]',
            'input[data-autom="gift-card-pin"]',
            # 备用选择器
            'input[id*="giftCard"]',
            'input[id*="gift_card"]',
            'input[type="text"][class*="form-textbox-input"]',
            'input[type="text"]'  # 最宽泛的选择器
        ]

        gift_card_input = None
        for selector in gift_card_selectors:
            try:
                task.add_log(f"🔍 尝试输入框选择器: {selector}", "info")
                temp_input = page.locator(selector).first
                await temp_input.wait_for(state='visible', timeout=3000)
                gift_card_input = temp_input
                task.add_log(f"✅ 找到礼品卡输入框: {selector}", "success")
                break
            except Exception as e:
                task.add_log(f"选择器 {selector} 失败: {e}", "warning")
                continue

        if gift_card_input is None:
            task.add_log("❌ 未找到礼品卡输入框", "error")
            await page.screenshot(path=f"no_gift_card_input_{task.id}.png")
            raise Exception("未找到礼品卡输入框")

        # 填写礼品卡号码（严格基于apple_automator.py）
        try:
            # 确保元素可交互
            await gift_card_input.wait_for(state='attached', timeout=5000)
            await gift_card_input.scroll_into_view_if_needed()

            # 清空并填写
            await gift_card_input.clear()
            await gift_card_input.fill(gift_card_number)

            task.add_log("✅ 礼品卡号码填写完成", "success")

            # 验证输入
            input_value = await gift_card_input.input_value()
            if input_value.strip() != gift_card_number:
                task.add_log(f"⚠️ 验证失败，重试... 期望: {gift_card_number}, 实际: {input_value}", "warning")
                await gift_card_input.clear()
                await page.wait_for_timeout(500)
                await gift_card_input.fill(gift_card_number)

            task.add_log("✅ 礼品卡号码填写和验证完成", "success")

        except Exception as e:
            task.add_log(f"❌ 填写礼品卡失败: {e}", "error")
            await page.screenshot(path=f"error_fill_gift_card_{task.id}.png")
            raise

    async def _check_gift_card_application_result(self, page: Page, task: Task):
        """检查礼品卡应用结果并记录 - 基于apple_automator.py"""
        task.add_log("🔍 检查礼品卡应用结果...", "info")

        try:
            # 检查成功消息
            success_selectors = [
                '.success',
                '.alert-success',
                '.notification-success',
                '.message-success',
                '.gift-card-success',
                'text="Gift card applied"',
                'text="Applied successfully"',
                'text="礼品卡已应用"'
            ]

            for selector in success_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        success_text = await element.text_content()
                        task.add_log(f"✅ 礼品卡应用成功: {success_text}", "success")
                        return
                except:
                    continue

            # 检查错误消息
            error_selectors = [
                '.error',
                '.alert-error',
                '.notification-error',
                '.message-error',
                '.gift-card-error',
                'text="Invalid gift card"',
                'text="Gift card not found"',
                'text="礼品卡无效"'
            ]

            for selector in error_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        error_text = await element.text_content()
                        task.add_log(f"❌ 礼品卡应用失败: {error_text}", "error")
                        return
                except:
                    continue

            # 检查页面上的总价变化
            try:
                total_selectors = [
                    '.total-price',
                    '.order-total',
                    '.grand-total',
                    '[data-testid*="total"]'
                ]

                for selector in total_selectors:
                    try:
                        total_element = page.locator(selector).first
                        if await total_element.count() > 0:
                            total_text = await total_element.text_content()
                            if total_text and ('$' in total_text or '￥' in total_text or '£' in total_text):
                                task.add_log(f"💰 当前订单总价: {total_text}", "info")
                                break
                    except:
                        continue
            except:
                pass

            task.add_log("ℹ️ 礼品卡应用状态不明确，请手动检查页面", "info")

        except Exception as e:
            task.add_log(f"⚠️ 检查礼品卡应用结果时出错: {e}", "warning")

    async def _wait_for_checkout_page_ready(self, page: Page, task: Task):
        """等待结账页面完全加载并准备好进行礼品卡操作 - 基于apple_automator.py"""
        task.add_log("⏳ 等待结账页面完全加载...", "info")

        # 等待页面基本加载
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        await page.wait_for_timeout(5000)  # 增加等待时间，确保页面完全稳定

        # 检查页面是否在正确的结账流程中
        current_url = page.url
        page_title = await page.title()

        task.add_log(f"当前页面: {current_url}", "info")
        task.add_log(f"页面标题: {page_title}", "info")

        # 验证是否在结账页面
        checkout_indicators = ['checkout', 'shipping', 'billing', 'payment']
        is_checkout_page = any(indicator in current_url.lower() for indicator in checkout_indicators)

        if not is_checkout_page:
            task.add_log("⚠️ 当前页面可能不是结账页面，继续尝试...", "warning")

        # 等待页面中的关键元素加载
        key_elements = [
            'form',  # 结账表单
            'input',  # 输入框
            'button'  # 按钮
        ]

        for element in key_elements:
            try:
                await page.wait_for_selector(element, timeout=10000)
                task.add_log(f"✅ 关键元素已加载: {element}", "info")
            except Exception as e:
                task.add_log(f"等待元素 {element} 超时: {e}", "warning")

        # 额外等待确保页面完全稳定
        await page.wait_for_timeout(2000)
        task.add_log("✅ 结账页面已准备就绪", "success")

    async def _click_gift_card_link(self, page: Page, task: Task):
        """步骤1: 寻找并点击礼品卡链接 - 严格基于apple_automator.py"""
        task.add_log("🔍 步骤1: 寻找礼品卡链接...", "info")

        # 等待页面稳定
        await page.wait_for_timeout(5000)  # 增加等待时间，确保页面完全稳定

        # 首先滚动页面确保所有元素可见
        await self._scroll_to_find_gift_card_section(page, task)

        # 严格按照apple_automator.py的礼品卡触发策略
        gift_card_strategies = [
            # 策略1: 通过具体文本匹配（Apple官网常见的礼品卡文本）
            lambda: page.locator('text="Do you have an Apple Gift Card?"').first,
            lambda: page.locator('text="Apply an Apple Gift Card"').first,
            lambda: page.locator('text="Enter your gift card number"').first,  # 关键！这是最重要的链接
            lambda: page.locator('text="Add gift card"').first,
            lambda: page.locator('text="Use gift card"').first,
            lambda: page.locator('text="Gift card"').first,

            # 策略2: 通过角色和文本查找
            lambda: page.locator('button:has-text("Gift Card")').first,
            lambda: page.locator('button:has-text("gift card")').first,
            lambda: page.locator('a:has-text("Gift Card")').first,
            lambda: page.locator('a:has-text("gift card")').first,
            lambda: page.locator('a:has-text("Enter your gift card number")').first,  # 重要的a标签

            # 策略3: 通过data属性查找
            lambda: page.locator('[data-autom*="gift"]').first,
            lambda: page.locator('[data-autom*="giftcard"]').first,
            lambda: page.locator('[data-analytics*="gift"]').first,

            # 策略4: 通过类名查找
            lambda: page.locator('.gift-card').first,
            lambda: page.locator('.giftcard').first,
            lambda: page.locator('.apple-gift-card').first,
        ]

        link_found = False
        for i, strategy in enumerate(gift_card_strategies, 1):
            try:
                task.add_log(f"🔍 尝试礼品卡链接策略 {i}...", "info")
                gift_card_link = strategy()

                # 检查元素是否存在
                count = await gift_card_link.count()
                task.add_log(f"  策略 {i}: 找到 {count} 个匹配元素", "info")

                if count == 0:
                    task.add_log(f"  策略 {i}: 没有找到匹配元素", "warning")
                    continue

                # 等待元素可见
                await gift_card_link.wait_for(state='visible', timeout=5000)
                task.add_log(f"  策略 {i}: 元素已可见", "info")

                # 滚动到元素位置
                await gift_card_link.scroll_into_view_if_needed()
                task.add_log(f"  策略 {i}: 已滚动到元素位置", "info")

                # 点击元素
                await gift_card_link.click()
                task.add_log(f"✅ 成功点击礼品卡链接 (策略{i})", "success")
                link_found = True
                break

            except Exception as e:
                task.add_log(f"❌ 礼品卡链接策略 {i} 失败: {e}", "warning")
                continue

        if not link_found:
            task.add_log("❌ 所有礼品卡链接策略都失败了！开始详细调试...", "error")

            # 调试1: 截图当前页面
            await page.screenshot(path=f"debug_no_gift_card_link_{task.id}.png")
            task.add_log(f"📸 已保存调试截图: debug_no_gift_card_link_{task.id}.png", "info")

            # 调试2: 保存页面HTML
            page_content = await page.content()
            with open(f"debug_no_gift_card_link_{task.id}.html", 'w', encoding='utf-8') as f:
                f.write(page_content)
            task.add_log(f"📄 已保存页面HTML: debug_no_gift_card_link_{task.id}.html", "info")

            # 调试3: 检查页面上是否有任何包含"gift"的文本
            await self._debug_search_gift_text(page, task)

            # 调试4: 检查页面上所有的链接和按钮
            await self._debug_print_all_links_and_buttons(page, task)

            # 尝试备用方法：直接查找礼品卡输入框
            task.add_log("🔄 尝试备用方法：直接查找礼品卡输入框...", "warning")
            if await self._try_direct_gift_card_input(page, task):
                task.add_log("✅ 通过备用方法找到礼品卡输入框", "success")
                return
            else:
                task.add_log("❌ 备用方法也失败了", "error")
                raise Exception("未找到礼品卡链接或输入框")

        # 等待页面响应
        await page.wait_for_timeout(2000)
        task.add_log("✅ 礼品卡链接点击完成，等待输入框出现", "success")

    async def _debug_search_gift_text(self, page: Page, task: Task):
        """调试：搜索页面上所有包含gift的文本"""
        try:
            task.add_log("🔍 调试：搜索页面上所有包含'gift'的文本...", "info")

            # 搜索所有包含gift的元素
            gift_elements = page.locator('*:has-text("gift"), *:has-text("Gift"), *:has-text("GIFT")')
            count = await gift_elements.count()
            task.add_log(f"📊 找到 {count} 个包含'gift'的元素", "info")

            for i in range(min(count, 10)):  # 最多显示10个
                try:
                    element = gift_elements.nth(i)
                    text = await element.text_content()
                    tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                    task.add_log(f"  {i+1}. <{tag_name}>: {text[:100]}...", "info")
                except Exception as e:
                    task.add_log(f"  {i+1}. 获取元素信息失败: {e}", "warning")

        except Exception as e:
            task.add_log(f"调试搜索gift文本失败: {e}", "warning")

    async def _debug_print_all_links_and_buttons(self, page: Page, task: Task):
        """调试：打印页面上所有的链接和按钮"""
        try:
            task.add_log("🔍 调试：检查页面上所有的链接和按钮...", "info")

            # 检查所有链接
            links = page.locator('a')
            link_count = await links.count()
            task.add_log(f"📊 找到 {link_count} 个链接", "info")

            for i in range(min(link_count, 20)):  # 最多显示20个
                try:
                    link = links.nth(i)
                    text = await link.text_content()
                    href = await link.get_attribute('href')
                    if text and text.strip():
                        task.add_log(f"  链接 {i+1}: '{text.strip()[:50]}' -> {href}", "info")
                except Exception as e:
                    task.add_log(f"  链接 {i+1}: 获取信息失败: {e}", "warning")

            # 检查所有按钮
            buttons = page.locator('button')
            button_count = await buttons.count()
            task.add_log(f"📊 找到 {button_count} 个按钮", "info")

            for i in range(min(button_count, 20)):  # 最多显示20个
                try:
                    button = buttons.nth(i)
                    text = await button.text_content()
                    if text and text.strip():
                        task.add_log(f"  按钮 {i+1}: '{text.strip()[:50]}'", "info")
                except Exception as e:
                    task.add_log(f"  按钮 {i+1}: 获取信息失败: {e}", "warning")

        except Exception as e:
            task.add_log(f"调试打印链接和按钮失败: {e}", "warning")

    async def _scroll_to_find_gift_card_section(self, page: Page, task: Task):
        """滚动页面寻找礼品卡相关区域 - 基于apple_automator.py"""
        task.add_log("🔄 滚动页面寻找礼品卡区域...", "info")

        # 首先尝试滚动到页面底部，因为礼品卡选项通常在付款区域
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

        # 然后尝试滚动到页面中部
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await page.wait_for_timeout(1000)

        # 最后滚动到顶部
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)

        task.add_log("✅ 页面滚动完成", "info")

    async def _try_direct_gift_card_input(self, page: Page, task: Task):
        """备用方法：直接查找礼品卡输入框，不依赖链接 - 基于apple_automator.py"""
        task.add_log("🔄 尝试直接查找礼品卡输入框...", "info")

        # 常见的礼品卡输入框选择器
        input_selectors = [
            'input[placeholder*="gift card"]',
            'input[placeholder*="Gift Card"]',
            'input[name*="gift"]',
            'input[name*="card"]',
            'input[id*="gift"]',
            'input[id*="card"]',
            '[data-autom*="gift"] input',
            '[data-autom*="card"] input'
        ]

        for selector in input_selectors:
            try:
                input_element = page.locator(selector).first
                if await input_element.count() > 0:
                    await input_element.scroll_into_view_if_needed()
                    task.add_log(f"✅ 找到礼品卡输入框: {selector}", "success")
                    return True
            except Exception as e:
                task.add_log(f"检查输入框 {selector} 失败: {e}", "warning")
                continue

        return False

    async def _fill_gift_card_input(self, page: Page, task: Task, gift_card_number: str):
        """步骤2: 填写礼品卡号码 - 严格基于apple_automator.py"""
        task.add_log("📝 步骤2: 填写礼品卡号码...", "info")

        # 确保礼品卡号码已正确解析
        if not gift_card_number:
            raise Exception("礼品卡号码未正确解析")

        task.add_log(f"准备输入礼品卡号码: {gift_card_number[:4]}****", "info")
        task.add_log(f"完整号码长度: {len(gift_card_number)} 字符", "info")

        # 等待输入框出现（点击链接后）
        await page.wait_for_timeout(3000)

        # 尝试多种礼品卡输入框选择器（严格基于apple_automator.py）
        gift_card_selectors = [
            'input[placeholder*="gift card"]',
            'input[placeholder*="Gift Card"]',
            'input[placeholder*="gift card number"]',
            'input[placeholder*="Enter your gift card"]',
            'input[name*="giftcard"]',
            'input[name*="giftCard"]',
            'input[name*="gift_card"]',
            'input[id*="giftcard"]',
            'input[id*="giftCard"]',
            'input[id*="gift_card"]',
            '[data-autom*="gift"], [data-autom*="card"]',
            'input[type="text"][placeholder*="Enter"]',
            '.gift-card input',
            '.giftcard input',
            'input[type="text"]'  # 更宽泛的选择器
        ]

        gift_card_input = None
        for selector in gift_card_selectors:
            try:
                task.add_log(f"尝试礼品卡选择器: {selector}", "info")
                temp_input = page.locator(selector).first
                await temp_input.wait_for(state='visible', timeout=3000)
                gift_card_input = temp_input
                task.add_log(f"✅ 找到礼品卡输入框: {selector}", "success")
                break
            except Exception as e:
                task.add_log(f"选择器 {selector} 失败: {e}", "warning")
                continue

        if gift_card_input is None:
            task.add_log("❌ 未找到礼品卡输入框，可能页面结构已变化", "error")
            # 截图用于调试
            await page.screenshot(path=f"no_gift_card_input_{gift_card_number[:4]}.png")
            raise Exception("未找到礼品卡输入框")

        # 填写礼品卡号码（严格基于apple_automator.py的方法）
        try:
            # 检查元素类型和可编辑性
            tag_name = await gift_card_input.evaluate('el => el.tagName.toLowerCase()')
            is_input = tag_name in ['input', 'textarea']
            is_contenteditable = await gift_card_input.evaluate('el => el.contentEditable === "true"')

            if not is_input and not is_contenteditable:
                task.add_log(f"❌ 礼品卡元素不可编辑: tagName={tag_name}", "error")
                raise Exception(f"礼品卡输入框不是可编辑元素: {tag_name}")

            # 确保元素可交互
            await gift_card_input.wait_for(state='attached', timeout=5000)
            await gift_card_input.scroll_into_view_if_needed()

            # 清空并填写
            if is_input:
                await gift_card_input.clear()
                await gift_card_input.fill(gift_card_number)
            else:
                # 对于contenteditable元素
                await gift_card_input.click()
                await gift_card_input.evaluate('el => el.textContent = ""')
                await gift_card_input.type(gift_card_number)

            task.add_log("✅ 礼品卡号码填写完成", "success")

            # 验证输入
            if is_input:
                input_value = await gift_card_input.input_value()
            else:
                input_value = await gift_card_input.text_content()

            if input_value.strip() != gift_card_number:
                task.add_log(f"⚠️ 礼品卡验证失败，重试... 期望: {gift_card_number}, 实际: {input_value}", "warning")
                if is_input:
                    await gift_card_input.clear()
                    await page.wait_for_timeout(500)
                    await gift_card_input.fill(gift_card_number)
                else:
                    await gift_card_input.click()
                    await gift_card_input.evaluate('el => el.textContent = ""')
                    await gift_card_input.type(gift_card_number)

            task.add_log("✅ 礼品卡号码填写和验证完成", "success")

        except Exception as e:
            task.add_log(f"❌ 填写礼品卡失败: {e}", "error")
            # 截图用于调试
            await page.screenshot(path=f"error_gift_card_{task.id}.png")
            # 保存页面HTML用于分析
            page_content = await page.content()
            with open(f"debug_gift_card_page_{task.id}.html", 'w', encoding='utf-8') as f:
                f.write(page_content)
            raise

    async def _try_direct_apple_gift_card_input(self, page: Page, task: Task, gift_card_number: str):
        """直接尝试Apple官网的礼品卡输入框 - 基于apple_automator.py"""
        task.add_log("🎯 尝试直接使用Apple官网礼品卡输入框...", "info")

        # Apple官网的精确选择器
        apple_selector = '#checkout\\.billing\\.billingOptions\\.selectedBillingOptions\\.giftCard\\.giftCardInput\\.giftCard'

        try:
            # 查找输入框
            input_element = page.locator(apple_selector).first

            # 检查是否存在
            if await input_element.count() == 0:
                task.add_log("Apple官网礼品卡输入框不存在", "info")
                return False

            # 检查是否可见和可用
            is_visible = await input_element.is_visible()
            is_enabled = await input_element.is_enabled()

            task.add_log(f"Apple官网礼品卡输入框状态: visible={is_visible}, enabled={is_enabled}", "info")

            if not (is_visible and is_enabled):
                return False

            # 滚动到元素位置
            await input_element.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)

            # 确保输入框获得焦点
            await input_element.focus()
            await page.wait_for_timeout(500)

            # 清空并填写
            await input_element.clear()
            await input_element.fill(gift_card_number)

            # 验证输入
            await page.wait_for_timeout(1000)
            input_value = await input_element.input_value()

            # Apple官网会自动格式化礼品卡号码（添加空格），所以需要去除空格进行比较
            input_value_clean = input_value.replace(' ', '').replace('-', '')
            expected_clean = gift_card_number.replace(' ', '').replace('-', '')

            if input_value_clean == expected_clean:
                task.add_log(f"✅ 成功填写Apple官网礼品卡号码: {input_value}", "success")
                task.add_log(f"原始输入: {gift_card_number}", "info")
                task.add_log(f"格式化后: {input_value}", "info")
                return True
            else:
                task.add_log(f"⚠️ 填写验证失败: 期望{expected_clean}, 实际{input_value_clean}", "warning")
                return False

        except Exception as e:
            task.add_log(f"⚠️ 直接填写Apple官网礼品卡输入框失败: {e}", "warning")
            return False

    async def _smart_find_and_fill_input(self, page: Page, task: Task, gift_card_number: str):
        """智能查找并填写礼品卡输入框 - 基于apple_automator.py"""
        # 策略1: 通用礼品卡输入框属性（排除Apple官网特定的，避免重复）
        primary_selectors = [
            # 通用礼品卡输入框
            'input[placeholder*="gift card" i]',
            'input[placeholder*="Gift Card" i]',
            'input[placeholder*="card number" i]',
            'input[placeholder*="PIN" i]',
            'input[placeholder*="Enter" i]',
            'input[name*="gift" i]',
            'input[name*="card" i]',
            'input[name*="pin" i]',
            'input[data-autom*="gift" i]',
            'input[data-autom*="card" i]',
            # 其他网站的礼品卡选择器
            'input[data-autom*="giftcard"]',
            'input[data-autom*="applygiftcard"]',
            'input[data-autom*="redeem"]'
        ]

        # 策略2: 通过上下文查找（在礼品卡相关区域内的输入框）
        contextual_selectors = [
            # 在礼品卡相关容器内的输入框
            '[class*="gift"] input[type="text"]',
            '[class*="gift"] input:not([type])',
            '[class*="card"] input[type="text"]',
            '[class*="card"] input:not([type])',
            '[data-autom*="gift"] input',
            '[data-autom*="card"] input',
            # 表单中的输入框
            'form input[type="text"]',
            'form input:not([type])',
            # 可能的Apple特定容器
            '.rs-giftcard input',
            '.giftcard-section input',
            '.payment-giftcard input',
            # 最近添加的输入框（可能是动态生成的）
            'input[type="text"]:last-of-type',
            'input:not([type]):last-of-type'
        ]

        # 策略3: 通用输入框（作为最后的备选）
        fallback_selectors = [
            'input[type="text"]',
            'input:not([type])',  # 没有指定type的input
            'input[maxlength="16"]',  # 可能是礼品卡长度
            'input[maxlength="20"]'
        ]

        # 按优先级尝试各种策略，一旦成功就立即返回
        all_strategies = [
            ("通用礼品卡属性", primary_selectors),
            ("上下文相关", contextual_selectors),
            ("通用输入框", fallback_selectors)
        ]

        for strategy_name, selectors in all_strategies:
            task.add_log(f"🔍 尝试{strategy_name}策略...", "info")
            for selector in selectors:
                if await self._try_fill_input_with_selector(page, task, selector, gift_card_number, strategy_name):
                    return True

        return False

    async def _try_fill_input_with_selector(self, page: Page, task: Task, selector: str, gift_card_number: str, strategy_name: str):
        """尝试使用特定选择器填写输入框 - 基于apple_automator.py"""
        try:
            elements = page.locator(selector)
            count = await elements.count()

            if count == 0:
                return False

            # 遍历所有匹配的元素
            for i in range(count):
                try:
                    input_element = elements.nth(i)

                    # 检查元素是否可见和可用
                    if not await input_element.is_visible() or not await input_element.is_enabled():
                        continue

                    # 获取输入框ID用于特殊处理
                    input_id = await input_element.get_attribute('id') or ''

                    # 如果是Apple官网的礼品卡输入框，直接使用
                    if 'giftCard' in input_id and 'giftCardInput' in input_id:
                        task.add_log(f"找到Apple官网礼品卡输入框: {input_id}", "info")
                        # 直接尝试填写，不需要额外验证
                    else:
                        # 智能验证：确保这是礼品卡输入框而不是其他输入框
                        if not await self._is_gift_card_input(input_element):
                            task.add_log(f"输入框 {i} 不是礼品卡输入框，跳过", "info")
                            continue

                    # 滚动到元素位置
                    await input_element.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)

                    # 确保输入框获得焦点
                    await input_element.focus()
                    await page.wait_for_timeout(500)

                    # 尝试多种填写方法
                    fill_success = False

                    # 方法1: 清空并填写
                    try:
                        await input_element.clear()
                        await input_element.fill(gift_card_number)
                        fill_success = True
                        task.add_log("使用clear+fill方法", "info")
                    except Exception as e:
                        task.add_log(f"clear+fill方法失败: {e}", "warning")

                    # 方法2: 选择全部并输入
                    if not fill_success:
                        try:
                            await input_element.select_text()
                            await input_element.fill(gift_card_number)
                            fill_success = True
                            task.add_log("使用select+fill方法", "info")
                        except Exception as e:
                            task.add_log(f"select+fill方法失败: {e}", "warning")

                    # 方法3: 键盘输入
                    if not fill_success:
                        try:
                            await input_element.click()
                            await page.keyboard.press('Control+a')  # 全选
                            await page.keyboard.type(gift_card_number)
                            fill_success = True
                            task.add_log("使用键盘输入方法", "info")
                        except Exception as e:
                            task.add_log(f"键盘输入方法失败: {e}", "warning")

                    if not fill_success:
                        task.add_log("所有填写方法都失败", "warning")
                        continue

                    # 验证输入
                    await page.wait_for_timeout(1000)
                    input_value = await input_element.input_value()

                    # 处理自动格式化的情况（如Apple官网会添加空格）
                    input_value_clean = input_value.replace(' ', '').replace('-', '')
                    expected_clean = gift_card_number.replace(' ', '').replace('-', '')

                    if input_value_clean == expected_clean:
                        task.add_log(f"✅ 成功填写礼品卡号码 ({strategy_name}): {selector}", "success")
                        task.add_log(f"输入值: {input_value}", "info")
                        task.add_log("🎯 礼品卡号码填写完成，准备点击Apply按钮", "success")
                        return True
                    else:
                        task.add_log(f"输入验证失败: 期望{expected_clean}, 实际{input_value_clean}", "warning")
                        # 清空错误输入
                        try:
                            await input_element.clear()
                        except:
                            pass
                        # 继续尝试下一个元素
                        continue

                except Exception as e:
                    task.add_log(f"尝试输入框 {i} 失败: {e}", "warning")
                    continue

        except Exception as e:
            task.add_log(f"选择器 {selector} 失败: {e}", "warning")

        return False

    async def _is_gift_card_input(self, input_element):
        """智能判断输入框是否为礼品卡输入框 - 基于apple_automator.py"""
        try:
            # 获取输入框属性
            placeholder = (await input_element.get_attribute('placeholder') or '').lower()
            name = (await input_element.get_attribute('name') or '').lower()
            id_attr = (await input_element.get_attribute('id') or '').lower()
            class_attr = (await input_element.get_attribute('class') or '').lower()
            data_autom = (await input_element.get_attribute('data-autom') or '').lower()

            # 礼品卡相关关键词（包括Apple官网特定的）
            gift_card_keywords = [
                'gift', 'card', 'pin', 'redeem', 'apply', 'giftcard',
                'giftcardinput'  # Apple官网特定的ID模式
            ]

            # 排除的关键词（税务、邮编等）
            exclude_keywords = [
                'tax', 'zip', 'postal', 'phone', 'email', 'address',
                'city', 'state', 'country', 'billing', 'shipping',
                'first', 'last', 'name', 'cvv', 'expiry', 'expire'
            ]

            # 检查是否包含礼品卡关键词
            all_attributes = f"{placeholder} {name} {id_attr} {class_attr} {data_autom}"
            has_gift_keywords = any(keyword in all_attributes for keyword in gift_card_keywords)
            has_exclude_keywords = any(keyword in all_attributes for keyword in exclude_keywords)

            # 如果包含排除关键词，则不是礼品卡输入框
            if has_exclude_keywords:
                return False

            # 如果包含礼品卡关键词，则可能是礼品卡输入框
            if has_gift_keywords:
                return True

            # 检查输入框的上下文（父元素）
            parent_element = input_element.locator('..')
            try:
                parent_class = (await parent_element.get_attribute('class') or '').lower()
                parent_data = (await parent_element.get_attribute('data-autom') or '').lower()
                parent_context = f"{parent_class} {parent_data}"

                has_parent_gift_keywords = any(keyword in parent_context for keyword in gift_card_keywords)
                has_parent_exclude_keywords = any(keyword in parent_context for keyword in exclude_keywords)

                if has_parent_exclude_keywords:
                    return False

                if has_parent_gift_keywords:
                    return True

            except Exception as e:
                pass

            # 默认情况下，如果没有明确的指标，则需要更谨慎
            return False

        except Exception as e:
            return False

    async def _fallback_input_search(self, page: Page, task: Task, gift_card_number: str):
        """备用策略：尝试更宽泛的输入框查找 - 基于apple_automator.py"""
        try:
            # 获取页面上所有的输入框
            all_inputs = page.locator('input')
            count = await all_inputs.count()

            task.add_log(f"备用策略：页面上共有 {count} 个输入框", "info")

            for i in range(count):
                try:
                    input_element = all_inputs.nth(i)

                    # 获取输入框基本信息
                    input_type = await input_element.get_attribute('type') or ''
                    placeholder = await input_element.get_attribute('placeholder') or ''
                    name = await input_element.get_attribute('name') or ''
                    id_attr = await input_element.get_attribute('id') or ''

                    task.add_log(f"输入框 {i}: type={input_type}, placeholder='{placeholder}', name='{name}', id='{id_attr}'", "info")

                    # 只尝试文本类型的输入框，并验证是否为礼品卡输入框
                    if input_type.lower() in ['text', 'password', '']:
                        # 智能验证：确保这是礼品卡输入框
                        if not await self._is_gift_card_input(input_element):
                            task.add_log(f"备用策略：输入框 {i} 不是礼品卡输入框，跳过", "info")
                            continue

                        # 尝试填写
                        await input_element.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)

                        if await input_element.is_enabled():
                            await input_element.clear()
                            await input_element.fill(gift_card_number)

                            # 验证输入
                            await page.wait_for_timeout(500)
                            input_value = await input_element.input_value()

                            if input_value == gift_card_number:
                                task.add_log(f"✅ 备用策略成功填写礼品卡号码到输入框 {i}", "success")
                                task.add_log(f"输入框属性: type={input_type}, placeholder='{placeholder}'", "info")
                                return True
                            else:
                                # 清空失败的输入
                                await input_element.clear()

                except Exception as e:
                    task.add_log(f"尝试输入框 {i} 失败: {e}", "warning")
                    continue

        except Exception as e:
            task.add_log(f"备用输入框查找失败: {e}", "warning")

        return False

    async def _debug_print_all_inputs(self, page: Page, task: Task):
        """打印页面上所有输入框的信息用于调试 - 基于apple_automator.py"""
        try:
            all_inputs = page.locator('input')
            count = await all_inputs.count()
            task.add_log(f"🔍 调试：页面上共有 {count} 个输入框", "info")

            for i in range(min(count, 20)):  # 最多显示20个
                try:
                    input_element = all_inputs.nth(i)
                    input_type = await input_element.get_attribute('type') or ''
                    placeholder = await input_element.get_attribute('placeholder') or ''
                    name = await input_element.get_attribute('name') or ''
                    id_attr = await input_element.get_attribute('id') or ''
                    class_attr = await input_element.get_attribute('class') or ''
                    is_visible = await input_element.is_visible()
                    is_enabled = await input_element.is_enabled()

                    task.add_log(f"输入框 {i}: type='{input_type}', placeholder='{placeholder}', name='{name}', id='{id_attr}', class='{class_attr}', visible={is_visible}, enabled={is_enabled}", "info")

                except Exception as e:
                    task.add_log(f"获取输入框 {i} 信息失败: {e}", "warning")

        except Exception as e:
            task.add_log(f"调试输入框信息失败: {e}", "warning")

    async def _apply_gift_card_and_get_feedback(self, page: Page, task: Task, gift_card_number: str = None):
        """点击Apply按钮并获取反馈，检测错误状态 - 增强版"""
        task.add_log("🔄 点击Apply按钮...", "info")

        # Apply按钮选择器
        apply_selectors = [
            'button:has-text("Apply")',
            'button:has-text("apply")',
            'input[type="submit"][value*="Apply"]',
            'input[type="submit"][value*="apply"]',
            '[data-testid*="apply"] button',
            '[data-autom*="apply"] button',
            'button[type="submit"]'
        ]

        apply_button = None
        for selector in apply_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.wait_for(state='visible', timeout=5000)
                    if await element.is_visible() and await element.is_enabled():
                        apply_button = element
                        task.add_log(f"✅ 找到Apply按钮: {selector}", "info")
                        break
            except:
                continue

        if not apply_button:
            raise Exception("无法找到Apply按钮")

        # 点击Apply按钮
        await apply_button.scroll_into_view_if_needed()
        await apply_button.click()
        task.add_log("✅ 已点击Apply按钮，等待结果...", "success")

        # 等待处理结果
        await page.wait_for_timeout(5000)

        # 使用新的错误检测方法替代旧的_check_gift_card_feedback
        await self._detect_and_update_gift_card_errors(page, task, gift_card_number)

    async def _check_gift_card_feedback(self, page: Page, task: Task):
        """检查礼品卡应用反馈 - 基于apple_automator.py"""
        task.add_log("🔍 检查礼品卡应用结果...", "info")

        # 检查错误消息
        error_selectors = [
            '.error',
            '.alert-error',
            '[role="alert"]',
            '.notification-error',
            '.message-error',
            '.invalid-gift-card',
            '.insufficient-balance'
        ]

        for selector in error_selectors:
            try:
                error_element = page.locator(selector).first
                if await error_element.count() > 0 and await error_element.is_visible():
                    error_text = await error_element.text_content()
                    if error_text and error_text.strip():
                        # 检查是否是余额不足的错误
                        if any(keyword in error_text.lower() for keyword in ['insufficient', 'not enough', 'balance', '余额不足']):
                            task.add_log(f"❌ 礼品卡余额不足: {error_text}", "error")
                            raise Exception(f"礼品卡余额不足: {error_text}")
                        else:
                            task.add_log(f"❌ 礼品卡应用失败: {error_text}", "error")
                            raise Exception(f"礼品卡应用失败: {error_text}")
            except Exception as e:
                if "礼品卡" in str(e):
                    raise e
                continue

        # 检查成功消息
        success_selectors = [
            '.success',
            '.alert-success',
            '.notification-success',
            '.message-success',
            '[data-testid*="success"]',
            '.gift-card-applied'
        ]

        for selector in success_selectors:
            try:
                success_element = page.locator(selector).first
                if await success_element.count() > 0 and await success_element.is_visible():
                    success_text = await success_element.text_content()
                    if success_text and success_text.strip():
                        task.add_log(f"✅ 礼品卡应用成功: {success_text}", "success")
                        return
            except:
                continue

        # 如果没有明确的成功/失败消息，检查页面变化
        task.add_log("⚠️ 礼品卡应用状态不明确，请手动检查页面", "warning")

    async def finalize_purchase(self, task: Task) -> bool:
        """完成购买 - 实际实现（但不执行最终提交）"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log("🎯 正在检查购买准备状态...", "info")

            # 等待页面加载
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            # 检查是否有错误消息（如余额不足等）
            error_selectors = [
                '.error',
                '.alert-error',
                '[role="alert"]',
                '.notification-error',
                '.message-error',
                '.payment-error',
                '.insufficient-funds'
            ]

            for selector in error_selectors:
                try:
                    error_element = page.locator(selector).first
                    if await error_element.count() > 0:
                        error_text = await error_element.text_content()
                        if error_text and error_text.strip():
                            task.add_log(f"❌ 发现错误信息: {error_text}", "error")
                            
                            # 检测余额不足错误
                            if self._is_insufficient_balance_error(error_text):
                                # 发送WebSocket事件
                                self._send_balance_error_event(task, error_text)
                                
                            return False
                except:
                    continue

            # 查找最终购买按钮（但不点击）
            purchase_selectors = [
                'button:has-text("Place Order")',
                'button:has-text("Complete Purchase")',
                'button:has-text("Buy Now")',
                'button:has-text("确认购买")',
                'button:has-text("立即购买")',
                'button:has-text("下单")',
                '[data-testid*="place-order"]',
                '[data-testid*="complete-purchase"]',
                '[data-autom*="place-order"]',
                '[data-autom*="purchase"]'
            ]

            purchase_button = None
            for selector in purchase_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.wait_for(state='visible', timeout=5000)
                        is_enabled = await element.is_enabled()
                        if is_enabled:
                            purchase_button = element
                            task.add_log(f"✅ 找到购买按钮: {selector}", "info")
                            break
                        else:
                            task.add_log(f"⚠️ 购买按钮存在但未启用: {selector}", "warning")
                except:
                    continue

            if not purchase_button:
                task.add_log("❌ 未找到最终购买按钮", "error")
                return False

            # 检查订单摘要和总价
            try:
                # 查找总价信息
                total_selectors = [
                    '.total-price',
                    '.order-total',
                    '.grand-total',
                    '[data-testid*="total"]',
                    '[data-testid*="price"]'
                ]

                for selector in total_selectors:
                    try:
                        total_element = page.locator(selector).first
                        if await total_element.count() > 0:
                            total_text = await total_element.text_content()
                            if total_text and ('$' in total_text or '￥' in total_text or '£' in total_text):
                                task.add_log(f"💰 订单总价: {total_text}", "info")
                                break
                    except:
                        continue
            except:
                pass

            # 重要：这里不执行实际的购买操作，只是验证准备状态
            task.add_log("⚠️ 购买准备完成，但为安全起见未执行最终提交", "warning")
            task.add_log("🔍 请手动检查订单详情并确认购买", "info")
            task.add_log("🎯 自动化流程已完成到购买确认页面", "success")

            # 保持浏览器打开，让用户手动确认
            task.add_log("🌐 浏览器将保持打开状态，供您手动确认", "info")

            return True

        except Exception as e:
            task.add_log(f"❌ 购买准备检查失败: {str(e)}", "error")
            return False

    async def _apply_existing_gift_cards(self, page: Page, task: Task):
        """应用已有的礼品卡信息（用户已经输入过）"""
        try:
            task.add_log("🎁 开始应用已有的礼品卡信息", "info")

            # 获取礼品卡信息
            gift_card_numbers = []
            if task.config.gift_cards:
                gift_card_numbers = [gc.number for gc in task.config.gift_cards]
                task.add_log(f"📋 从gift_cards获取到 {len(gift_card_numbers)} 张礼品卡", "info")
            elif task.config.gift_card_code:  # 向后兼容
                gift_card_numbers = [task.config.gift_card_code]
                task.add_log(f"📋 从gift_card_code获取到礼品卡: {task.config.gift_card_code[:4]}****", "info")

            if not gift_card_numbers:
                raise Exception("没有找到礼品卡信息")

            # 应用每张礼品卡
            for i, gift_card_number in enumerate(gift_card_numbers, 1):
                task.add_log(f"🎯 应用第 {i} 张礼品卡: {gift_card_number[:4]}****", "info")

                try:
                    # 对于第一张礼品卡，需要点击链接打开输入框
                    if i == 1:
                        task.add_log("🔗 点击'Enter your gift card number'链接...", "info")
                        await self._sota_click_gift_card_link(page, task)

                    # 填写礼品卡号码
                    task.add_log(f"📝 填写第 {i} 张礼品卡号码...", "info")
                    await self._sota_fill_gift_card_input(page, task, gift_card_number)

                    # 点击Apply按钮
                    task.add_log(f"✅ 点击Apply按钮应用第 {i} 张礼品卡...", "info")
                    await self._apply_gift_card_and_get_feedback(page, task, gift_card_number)

                    task.add_log(f"🎉 第 {i} 张礼品卡应用完成", "success")

                    # 如果还有更多礼品卡，等待页面更新并准备下一张
                    if i < len(gift_card_numbers):
                        await page.wait_for_timeout(2000)
                        task.add_log(f"🔄 准备添加下一张礼品卡 ({i + 1}/{len(gift_card_numbers)})", "info")
                        await self._click_add_another_card(page, task)

                except Exception as e:
                    task.add_log(f"❌ 第 {i} 张礼品卡应用失败: {e}", "error")
                    # 继续处理下一张礼品卡
                    continue

            task.add_log("✅ 所有礼品卡应用完成", "success")

        except Exception as e:
            task.add_log(f"❌ 应用已有礼品卡失败: {str(e)}", "error")
            raise

    async def _handle_gift_card_input(self, page: Page, task: Task):
        """处理礼品卡输入 - 等待用户通过前端输入礼品卡信息"""
        import time
        import asyncio

        try:
            task.add_log("🎁 到达礼品卡输入阶段，等待用户输入...", "info")

            # 更新任务状态为等待礼品卡输入
            task.status = TaskStatus.WAITING_GIFT_CARD_INPUT
            self._send_step_update(task, "waiting_gift_card_input", "waiting", 80, "等待用户输入礼品卡信息")

            # 发送礼品卡输入请求到前端
            if hasattr(self, 'message_service') and self.message_service:
                self.message_service.publish('gift_card_input_required', {
                    'task_id': task.id,
                    'message': '请输入礼品卡信息',
                    'timestamp': time.time()
                })
                task.add_log("✅ 已发送礼品卡输入请求到前端", "info")

            # 等待用户输入（通过检查任务状态变化）
            task.add_log("⏳ 等待用户通过前端输入礼品卡信息...", "info")

            # 轮询等待用户输入（最多等待10分钟）
            max_wait_time = 600  # 10分钟
            check_interval = 2   # 每2秒检查一次
            waited_time = 0

            while waited_time < max_wait_time:
                await asyncio.sleep(check_interval)
                waited_time += check_interval

                # 重新获取任务状态（可能被其他地方更新）
                current_task = self.task_manager.get_task(task.id) if hasattr(self, 'task_manager') else task

                # 如果状态不再是等待输入，说明用户已经提交了
                if current_task and current_task.status != TaskStatus.WAITING_GIFT_CARD_INPUT:
                    task.add_log("✅ 检测到用户已提交礼品卡信息，继续执行", "success")
                    # 更新本地任务对象的状态和配置
                    task.status = current_task.status
                    task.config = current_task.config
                    return

                # 每30秒提醒一次
                if waited_time % 30 == 0:
                    task.add_log(f"⏳ 仍在等待用户输入礼品卡信息... (已等待 {waited_time//60} 分钟)", "info")

            # 超时处理
            task.add_log("⚠️ 等待用户输入超时（10分钟），任务暂停", "warning")
            raise Exception("等待用户输入礼品卡信息超时")

        except Exception as e:
            task.add_log(f"❌ 礼品卡输入处理失败: {str(e)}", "error")
            raise

    async def cleanup_task(self, task_id: str, force_close: bool = False):
        """清理任务资源 - 可选择是否强制关闭浏览器"""
        if not force_close:
            # 默认情况下不关闭浏览器，让用户手动检查
            logger.info(f"保持任务 {task_id} 的浏览器打开状态")
            return

        if task_id in self.pages:
            try:
                await self.pages[task_id].close()
                del self.pages[task_id]
                logger.info(f"已关闭任务 {task_id} 的页面")
            except Exception as e:
                logger.warning(f"关闭页面失败: {e}")

        if task_id in self.contexts:
            try:
                await self.contexts[task_id].close()
                del self.contexts[task_id]
                logger.info(f"已关闭任务 {task_id} 的浏览器上下文")
            except Exception as e:
                logger.warning(f"关闭浏览器上下文失败: {e}")
    
    async def cleanup_all(self):
        """清理所有资源"""
        for task_id in list(self.contexts.keys()):
            await self.cleanup_task(task_id)
            
        if self.browser:
            await self.browser.close()
            
        if self.playwright:
            await self.playwright.stop()

    # ==================== 基于apple_automator.py的选择方法 ====================

    async def _apple_select_model(self, page: Page, label: str, task: Task) -> bool:
        """选择iPhone型号 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择型号: {label}", "info")

            # 等待型号选择区域加载
            await page.wait_for_selector('[data-analytics-section="dimensionScreensize"]', timeout=20000)

            # 尝试多种选择器
            selectors = [
                f'text="{label}"',
                f'text={label}',
                f'[aria-label*="{label}"]',
                f'button:has-text("{label}")',
                f'label:has-text("{label}")',
                f'input[value*="{label}"] + label',
            ]

            for selector in selectors:
                try:
                    task.add_log(f"尝试型号选择器: {selector}", "info")
                    element = page.locator(selector).first
                    await element.wait_for(state='visible', timeout=5000)
                    await element.scroll_into_view_if_needed()
                    await element.click()
                    task.add_log(f"成功点击型号: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"型号选择器 {selector} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到型号选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"型号选择异常: {str(e)}", "error")
            return False

    async def _apple_select_finish(self, page: Page, label: str, task: Task) -> bool:
        """选择颜色/表面处理 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择颜色: {label}", "info")

            # 等待颜色选择区域加载
            await page.wait_for_selector('[data-analytics-section="dimensionColor"]', timeout=20000)

            # 尝试多种颜色选择策略
            strategies = [
                # 策略1: 直接文本匹配
                lambda: self._try_finish_text_match(page, label),
                # 策略2: 通过fieldset查找
                lambda: self._try_finish_fieldset_match(page, label),
                # 策略3: 通过按钮查找
                lambda: self._try_finish_button_match(page, label),
                # 策略4: 通过radio button查找
                lambda: self._try_finish_radio_match(page, label),
            ]

            for i, strategy in enumerate(strategies, 1):
                try:
                    task.add_log(f"尝试颜色选择策略 {i}", "info")
                    await strategy()
                    task.add_log(f"成功选择颜色: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"颜色选择策略 {i} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到颜色选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"颜色选择异常: {str(e)}", "error")
            return False

    async def _apple_select_storage(self, page: Page, label: str, task: Task) -> bool:
        """选择存储容量 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择存储容量: {label}", "info")

            # 等待存储选择区域加载
            await page.wait_for_selector('[data-analytics-section="dimensionCapacity"]', timeout=20000)

            # 尝试多种存储选择策略
            strategies = [
                # 策略1: 直接文本匹配
                lambda: self._try_storage_text_match(page, label),
                # 策略2: 通过fieldset查找
                lambda: self._try_storage_fieldset_match(page, label),
                # 策略3: 通过按钮查找
                lambda: self._try_storage_button_match(page, label),
                # 策略4: 通过radio button查找
                lambda: self._try_storage_radio_match(page, label),
            ]

            for i, strategy in enumerate(strategies, 1):
                try:
                    task.add_log(f"尝试存储选择策略 {i}", "info")
                    await strategy()
                    task.add_log(f"成功选择存储: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"存储选择策略 {i} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到存储选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"存储选择异常: {str(e)}", "error")
            return False

    async def _apple_select_trade_in(self, page: Page, label: str, task: Task) -> bool:
        """选择Trade In选项 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择Trade In: {label}", "info")

            # 首先等待Trade In区域出现并启用
            await self._wait_for_trade_in_enabled(page, task)

            # 尝试多种Trade In选择策略（基于apple_automator.py）
            strategies = [
                # 策略1: 通过具体的radio button ID
                lambda: self._try_tradein_radio_id_match(page, label),
                # 策略2: 直接文本匹配
                lambda: self._try_tradein_text_match(page, label),
                # 策略3: 通过fieldset查找
                lambda: self._try_tradein_fieldset_match(page, label),
                # 策略4: 通过按钮查找
                lambda: self._try_tradein_button_match(page, label),
                # 策略5: 通过radio button查找
                lambda: self._try_tradein_radio_match(page, label),
            ]

            for i, strategy in enumerate(strategies, 1):
                try:
                    task.add_log(f"尝试Trade In选择策略 {i}", "info")
                    await strategy()
                    task.add_log(f"成功选择Trade In: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"Trade In选择策略 {i} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到Trade In选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"Trade In选择异常: {str(e)}", "error")
            return False

    async def _apple_select_payment(self, page: Page, label: str, task: Task) -> bool:
        """选择Payment选项 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择Payment: {label}", "info")

            # 首先等待Payment区域出现并启用
            await self._wait_for_payment_enabled(page, task)

            # 尝试多种Payment选择策略（基于apple_automator.py）
            strategies = [
                # 策略1: 通过具体的radio button ID
                lambda: self._try_payment_radio_id_match(page, label),
                # 策略2: 直接文本匹配
                lambda: self._try_payment_text_match(page, label),
                # 策略3: 通过fieldset查找
                lambda: self._try_payment_fieldset_match(page, label),
                # 策略4: 通过按钮查找
                lambda: self._try_payment_button_match(page, label),
                # 策略5: 通过radio button查找
                lambda: self._try_payment_radio_match(page, label),
            ]

            for i, strategy in enumerate(strategies, 1):
                try:
                    task.add_log(f"尝试Payment选择策略 {i}", "info")
                    await strategy()
                    task.add_log(f"成功选择Payment: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"Payment选择策略 {i} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到Payment选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"Payment选择异常: {str(e)}", "error")
            return False

    async def _apple_select_applecare(self, page: Page, label: str, task: Task) -> bool:
        """选择AppleCare选项 - 基于apple_automator.py"""
        try:
            task.add_log(f"选择AppleCare: {label}", "info")

            # 首先等待AppleCare区域出现并启用
            await self._wait_for_applecare_enabled(page, task)

            # 尝试多种AppleCare选择策略（基于apple_automator.py）
            strategies = [
                # 策略1: 通过具体的data-autom属性
                lambda: self._try_applecare_autom_match(page, label),
                # 策略2: 直接文本匹配
                lambda: self._try_applecare_text_match(page, label),
                # 策略3: 通过fieldset查找
                lambda: self._try_applecare_fieldset_match(page, label),
                # 策略4: 通过按钮查找
                lambda: self._try_applecare_button_match(page, label),
                # 策略5: 通过radio button查找
                lambda: self._try_applecare_radio_match(page, label),
            ]

            for i, strategy in enumerate(strategies, 1):
                try:
                    task.add_log(f"尝试AppleCare选择策略 {i}", "info")
                    await strategy()
                    task.add_log(f"成功选择AppleCare: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"AppleCare选择策略 {i} 失败: {e}", "warning")
                    continue

            task.add_log(f"无法找到AppleCare选项: {label}", "error")
            return False

        except Exception as e:
            task.add_log(f"AppleCare选择异常: {str(e)}", "error")
            return False

    # ==================== 等待方法 ====================

    async def _wait_for_trade_in_enabled(self, page: Page, task: Task):
        """等待Trade In区域启用"""
        try:
            task.add_log("等待Trade In区域启用...", "info")
            await page.wait_for_selector('[data-analytics-section="tradein"]', timeout=30000)
            await page.wait_for_timeout(2000)
            task.add_log("Trade In区域已启用", "success")
        except Exception as e:
            task.add_log(f"等待Trade In区域失败: {e}", "warning")

    async def _wait_for_payment_enabled(self, page: Page, task: Task):
        """等待Payment区域启用 - 基于apple_automator.py"""
        try:
            task.add_log("等待Payment区域启用...", "info")

            # 等待Payment区域出现
            await page.wait_for_selector('[data-analytics-section="paymentOptions"]', timeout=15000)

            # 等待fieldset不再被禁用
            max_wait_time = 20  # 最多等待20秒
            wait_interval = 0.5   # 每0.5秒检查一次

            for i in range(int(max_wait_time / wait_interval)):
                try:
                    # 检查fieldset是否还有disabled属性
                    fieldset = page.locator('[data-analytics-section="paymentOptions"] fieldset').first
                    is_disabled = await fieldset.get_attribute('disabled')

                    if is_disabled is None:
                        task.add_log(f"Payment区域已启用 (等待了{(i+1)*wait_interval:.1f}秒)", "success")
                        await page.wait_for_timeout(500)  # 额外等待0.5秒确保完全加载
                        return

                    # 尝试强制启用 - 移除disabled属性
                    if i > 10:  # 等待5秒后尝试强制启用
                        try:
                            await page.evaluate("""
                                const fieldset = document.querySelector('[data-analytics-section="paymentOptions"] fieldset');
                                if (fieldset && fieldset.hasAttribute('disabled')) {
                                    fieldset.removeAttribute('disabled');
                                    // 同时启用所有input元素
                                    const inputs = fieldset.querySelectorAll('input[disabled]');
                                    inputs.forEach(input => input.removeAttribute('disabled'));
                                }
                            """)
                            task.add_log("尝试强制启用Payment区域", "info")
                        except Exception as e:
                            task.add_log(f"强制启用失败: {e}", "warning")

                    await page.wait_for_timeout(int(wait_interval * 1000))

                except Exception as e:
                    task.add_log(f"检查Payment状态时出错: {e}", "warning")
                    await page.wait_for_timeout(int(wait_interval * 1000))

            task.add_log("Payment区域在20秒内未启用，尝试强制继续...", "warning")

        except Exception as e:
            task.add_log(f"等待Payment区域失败: {e}", "warning")

    async def _wait_for_applecare_enabled(self, page: Page, task: Task):
        """等待AppleCare区域启用 - 基于apple_automator.py"""
        try:
            task.add_log("等待AppleCare区域启用...", "info")

            # 等待AppleCare区域出现
            await page.wait_for_selector('[data-analytics-section="applecare"]', timeout=15000)

            # 等待AppleCare选项不再被禁用
            max_wait_time = 20  # 最多等待20秒
            wait_interval = 0.5   # 每0.5秒检查一次

            for i in range(int(max_wait_time / wait_interval)):
                try:
                    # 检查AppleCare选项是否还有disabled属性
                    applecare_input = page.locator('[data-autom="noapplecare"]').first
                    is_disabled = await applecare_input.get_attribute('disabled')

                    if is_disabled is None:
                        task.add_log(f"AppleCare区域已启用 (等待了{(i+1)*wait_interval:.1f}秒)", "success")
                        await page.wait_for_timeout(500)  # 额外等待0.5秒确保完全加载
                        return

                    await page.wait_for_timeout(int(wait_interval * 1000))

                except Exception as e:
                    task.add_log(f"检查AppleCare状态时出错: {e}", "warning")
                    await page.wait_for_timeout(int(wait_interval * 1000))

            task.add_log("AppleCare区域在20秒内未启用，尝试强制继续...", "warning")

        except Exception as e:
            task.add_log(f"等待AppleCare区域失败: {e}", "warning")

    # ==================== Trade In选择策略 ====================

    async def _try_tradein_radio_id_match(self, page: Page, label: str):
        """策略1: 通过具体的radio button ID匹配 - 基于apple_automator.py"""
        # 根据标签确定对应的ID
        if "No trade-in" in label or "No trade in" in label:
            radio_id = "noTradeIn"
            label_id = "noTradeIn_label"
        elif "Select a smartphone" in label:
            radio_id = "tradeIn"
            label_id = "tradeIn_label"
        else:
            raise Exception(f"未知的Trade In标签: {label}")

        # 尝试点击radio button
        try:
            radio_button = page.locator(f'#{radio_id}')
            await radio_button.wait_for(state='visible', timeout=5000)
            await radio_button.scroll_into_view_if_needed()
            await radio_button.click()
            return
        except:
            pass

        # 尝试点击label
        try:
            label_element = page.locator(f'#{label_id}')
            await label_element.wait_for(state='visible', timeout=5000)
            await label_element.scroll_into_view_if_needed()
            await label_element.click()
            return
        except:
            pass

        # 尝试点击包含文本的label
        try:
            label_element = page.locator(f'label[for="{radio_id}"]')
            await label_element.wait_for(state='visible', timeout=5000)
            await label_element.scroll_into_view_if_needed()
            await label_element.click()
            return
        except:
            pass

        raise Exception(f"所有radio ID匹配策略都失败了: {radio_id}")

    async def _try_tradein_text_match(self, page: Page, label: str):
        """策略2: Trade In直接文本匹配 - 基于apple_automator.py"""
        selectors = [
            f'text="{label}"',
            f'text={label}',
            f'[data-analytics-section*="tradein"] text="{label}"',
            f'[data-analytics-section*="tradeIn"] text="{label}"',
        ]

        for selector in selectors:
            element = page.locator(selector).first
            await element.wait_for(state='visible', timeout=3000)
            await element.scroll_into_view_if_needed()
            await element.click()
            return

    async def _try_tradein_fieldset_match(self, page: Page, label: str):
        """策略3: 通过fieldset查找Trade In - 基于apple_automator.py"""
        # 查找包含trade in的fieldset
        fieldset = page.locator('fieldset').filter(has_text='trade').or_(
            page.locator('fieldset').filter(has_text='Trade')
        ).or_(
            page.locator('[data-analytics-section*="tradein"] fieldset')
        ).first

        await fieldset.wait_for(state='visible', timeout=5000)

        # 在fieldset内查找选项
        option = fieldset.locator(f'text="{label}"').or_(
            fieldset.locator(f'[aria-label*="{label}"]')
        ).or_(
            fieldset.locator(f'label:has-text("{label}")')
        ).first

        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_tradein_button_match(self, page: Page, label: str):
        """策略4: 通过按钮查找Trade In - 基于apple_automator.py"""
        selectors = [
            f'button:has-text("{label}")',
            f'[role="button"]:has-text("{label}")',
            f'[data-analytics-section*="tradein"] button:has-text("{label}")',
            f'[data-analytics-section*="tradeIn"] button:has-text("{label}")',
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=3000)
                await element.scroll_into_view_if_needed()
                await element.click()
                return
            except:
                continue

        raise Exception("所有Trade In按钮匹配策略都失败了")

    async def _try_tradein_radio_match(self, page: Page, label: str):
        """策略5: 通过radio button查找Trade In - 基于apple_automator.py"""
        selectors = [
            f'input[type="radio"][value*="{label}"] + label',
            f'input[type="radio"][aria-label*="{label}"]',
            f'[role="radio"][aria-label*="{label}"]',
            f'input[name*="trade"][value*="{label}"] + label',
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=3000)
                await element.scroll_into_view_if_needed()
                await element.click()
                return
            except:
                continue

        raise Exception("所有Trade In radio匹配策略都失败了")

    # ==================== Payment选择策略 ====================

    async def _try_payment_radio_id_match(self, page: Page, label: str):
        """策略1: 通过具体的radio button ID匹配 - 基于apple_automator.py"""
        # 根据标签确定对应的value和data-autom属性
        if "Buy" in label:
            value = "fullprice"
            autom = "purchaseGroupOptionfullprice"
        elif "Monthly" in label or "finance" in label.lower():
            value = "finance"
            autom = "purchaseGroupOptionfinance"
        else:
            raise Exception(f"未知的Payment标签: {label}")

        # 尝试通过value属性查找
        try:
            radio_button = page.locator(f'[data-analytics-section="paymentOptions"] input[value="{value}"]')
            await radio_button.wait_for(state='visible', timeout=3000)
            await radio_button.scroll_into_view_if_needed()
            await radio_button.click()
            return
        except:
            pass

        # 尝试通过data-autom属性查找
        try:
            radio_button = page.locator(f'[data-autom="{autom}"]')
            await radio_button.wait_for(state='visible', timeout=3000)
            await radio_button.scroll_into_view_if_needed()
            await radio_button.click()
            return
        except:
            pass

        # 尝试通过对应的label查找
        try:
            label_element = page.locator(f'[data-analytics-section="paymentOptions"] label:has-text("{label}")')
            await label_element.wait_for(state='visible', timeout=3000)
            await label_element.scroll_into_view_if_needed()
            await label_element.click()
            return
        except:
            pass

        # 尝试通过包含关键词的label查找
        try:
            if "Buy" in label:
                search_text = "Buy"
            elif "Monthly" in label:
                search_text = "Monthly payments"
            else:
                search_text = label

            label_element = page.locator(f'[data-analytics-section="paymentOptions"] label:has-text("{search_text}")')
            await label_element.wait_for(state='visible', timeout=3000)
            await label_element.scroll_into_view_if_needed()
            await label_element.click()
            return
        except:
            pass

        raise Exception(f"所有Payment radio ID匹配策略都失败了: {label}")

    async def _try_payment_text_match(self, page: Page, label: str):
        """策略2: Payment直接文本匹配 - 基于apple_automator.py"""
        selectors = [
            f'text="{label}"',
            f'text={label}',
            f'[data-analytics-section*="payment"] text="{label}"',
            f'[data-analytics-section*="financing"] text="{label}"',
        ]

        for selector in selectors:
            element = page.locator(selector).first
            await element.wait_for(state='visible', timeout=3000)
            await element.scroll_into_view_if_needed()
            await element.click()
            return

    async def _try_payment_fieldset_match(self, page: Page, label: str):
        """策略3: 通过fieldset查找Payment - 基于apple_automator.py"""
        # 查找包含payment的fieldset
        fieldset = page.locator('fieldset').filter(has_text='payment').or_(
            page.locator('fieldset').filter(has_text='Payment')
        ).or_(
            page.locator('fieldset').filter(has_text='financing')
        ).or_(
            page.locator('[data-analytics-section*="payment"] fieldset')
        ).first

        await fieldset.wait_for(state='visible', timeout=5000)

        # 在fieldset内查找选项
        option = fieldset.locator(f'text="{label}"').or_(
            fieldset.locator(f'[aria-label*="{label}"]')
        ).or_(
            fieldset.locator(f'label:has-text("{label}")')
        ).first

        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_payment_button_match(self, page: Page, label: str):
        """策略4: 通过按钮查找Payment - 基于apple_automator.py"""
        selectors = [
            f'button:has-text("{label}")',
            f'[role="button"]:has-text("{label}")',
            f'[data-analytics-section*="payment"] button:has-text("{label}")',
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=3000)
                await element.scroll_into_view_if_needed()
                await element.click()
                return
            except:
                continue

        raise Exception("所有Payment按钮匹配策略都失败了")

    async def _try_payment_radio_match(self, page: Page, label: str):
        """策略5: 通过radio button查找Payment - 基于apple_automator.py"""
        selectors = [
            f'input[type="radio"][value*="{label}"] + label',
            f'input[type="radio"][aria-label*="{label}"]',
            f'[role="radio"][aria-label*="{label}"]',
            f'input[name*="payment"][value*="{label}"] + label',
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=3000)
                await element.scroll_into_view_if_needed()
                await element.click()
                return
            except:
                continue

        raise Exception("所有Payment radio匹配策略都失败了")

    # ==================== AppleCare选择策略 ====================

    async def _try_applecare_autom_match(self, page: Page, label: str):
        """策略1: 通过具体的data-autom属性 - 基于apple_automator.py"""
        if "No AppleCare" in label or "No coverage" in label:
            selector = '[data-autom="noapplecare"]'
        else:
            selector = f'[data-autom*="applecare"][data-autom*="{label.lower()}"]'

        element = page.locator(selector).first
        await element.wait_for(state='visible', timeout=10000)
        await element.scroll_into_view_if_needed()
        await element.click()

    async def _try_applecare_text_match(self, page: Page, label: str):
        """策略2: AppleCare直接文本匹配 - 基于apple_automator.py"""
        selectors = [
            f'text="{label}"',
            f'text={label}',
            f'text="No AppleCare+ Coverage"',
            f'text*="No AppleCare"',
            f'text*="No coverage"',
            f'[data-analytics-section*="applecare"] text*="{label}"'
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=5000)
                await element.scroll_into_view_if_needed()
                await element.click()
                return
            except:
                continue
        raise Exception("No AppleCare text match found")

    async def _try_applecare_fieldset_match(self, page: Page, label: str):
        """策略3: 通过fieldset查找AppleCare - 基于apple_automator.py"""
        fieldset = page.locator('[data-analytics-section*="applecare"] fieldset').first
        await fieldset.wait_for(state='visible', timeout=10000)

        # 在fieldset中查找匹配的选项
        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_applecare_button_match(self, page: Page, label: str):
        """策略4: 通过按钮查找AppleCare - 基于apple_automator.py"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_applecare_radio_match(self, page: Page, label: str):
        """策略5: 通过radio button查找AppleCare - 基于apple_automator.py"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    # ==================== 颜色和存储选择策略 ====================

    async def _try_finish_text_match(self, page: Page, label: str):
        """通过文本匹配选择颜色"""
        selectors = [
            f'[data-analytics-section="dimensionColor"] text="{label}"',
            f'[data-analytics-section="dimensionColor"] text*="{label}"',
            f'text="{label}"',
            f'text*="{label}"'
        ]

        for selector in selectors:
            element = page.locator(selector).first
            await element.wait_for(state='visible', timeout=5000)
            await element.scroll_into_view_if_needed()
            await element.click()
            return

    async def _try_finish_fieldset_match(self, page: Page, label: str):
        """通过fieldset查找颜色"""
        fieldset = page.locator('fieldset:has-text("finish")').or_(
            page.locator('fieldset:has-text("color")')
        ).first
        await fieldset.wait_for(state='visible', timeout=10000)

        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_finish_button_match(self, page: Page, label: str):
        """通过按钮查找颜色"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_finish_radio_match(self, page: Page, label: str):
        """通过radio button查找颜色"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    async def _try_storage_text_match(self, page: Page, label: str):
        """通过文本匹配选择存储"""
        selectors = [
            f'[data-analytics-section="dimensionCapacity"] text="{label}"',
            f'[data-analytics-section="dimensionCapacity"] text*="{label}"',
            f'text="{label}"',
            f'text*="{label}"'
        ]

        for selector in selectors:
            element = page.locator(selector).first
            await element.wait_for(state='visible', timeout=5000)
            await element.scroll_into_view_if_needed()
            await element.click()
            return

    async def _try_storage_fieldset_match(self, page: Page, label: str):
        """通过fieldset查找存储"""
        fieldset = page.locator('fieldset:has-text("capacity")').or_(
            page.locator('fieldset:has-text("storage")')
        ).first
        await fieldset.wait_for(state='visible', timeout=10000)

        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_storage_button_match(self, page: Page, label: str):
        """通过按钮查找存储"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_storage_radio_match(self, page: Page, label: str):
        """通过radio button查找存储"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    # ==================== 增强的礼品卡错误检测方法 ====================
    
    async def _detect_and_update_gift_card_errors(self, page: Page, task: Task, gift_card_number: str = None):
        """检测礼品卡错误并更新状态到数据库"""
        try:
            task.add_log("🔍 检测礼品卡应用结果...", "info")

            # 等待页面加载完成
            await page.wait_for_timeout(3000)

            # 获取页面文本内容
            page_content = await page.content()

            # 定义错误消息和对应状态（修正状态映射）
            error_patterns = {
                "Please use an Apple Gift Card that has been purchased in United Kingdom": {
                    "status": "非本国卡",
                    "message": "非英国购买的礼品卡",
                    "log_level": "error"
                },
                "You have entered an invalid gift card. Please check the card number and pin and try again": {
                    "status": "被充值",
                    "message": "礼品卡已被使用或无效",
                    "log_level": "error"
                },
                "This gift card has a zero balance": {
                    "status": "0余额",
                    "message": "礼品卡余额为零",
                    "log_level": "warning"
                }
            }

            detected_error = None
            error_info = None

            # 检测错误模式
            for error_pattern, info in error_patterns.items():
                if error_pattern in page_content:
                    detected_error = error_pattern
                    error_info = info
                    task.add_log(f"🚨 检测到礼品卡错误: {error_pattern}", info["log_level"])
                    break

            # 如果检测到错误且有礼品卡号码
            if detected_error and gift_card_number:
                task.add_log(f"📝 更新礼品卡状态: {gift_card_number[:4]}**** -> {error_info['status']}", "warning")

                # 更新数据库中的礼品卡状态
                await self._update_gift_card_status_in_db(gift_card_number, error_info["status"])

                # 更新任务配置中的礼品卡状态
                if hasattr(task.config, 'gift_cards') and task.config.gift_cards:
                    for gift_card in task.config.gift_cards:
                        if hasattr(gift_card, 'number') and gift_card.number == gift_card_number:
                            gift_card.error_message = error_info["message"]
                            gift_card.expected_status = error_info["status"]
                            break

                # 发送WebSocket通知前端更新礼品卡状态
                await self._notify_gift_card_status_update(gift_card_number, error_info["status"], error_info["message"])

                # 抛出异常以停止当前礼品卡的处理
                raise Exception(f"礼品卡错误: {error_info['message']}")

            # 如果没有检测到错误，说明礼品卡应用成功
            if not detected_error:
                task.add_log("✅ 礼品卡应用成功，未检测到错误", "success")

                # 如果成功，更新为有额度状态
                if gift_card_number:
                    await self._update_gift_card_status_in_db(gift_card_number, "有额度")
                    await self._notify_gift_card_status_update(gift_card_number, "有额度", "礼品卡应用成功")
                    
        except Exception as e:
            task.add_log(f"⚠️ 礼品卡错误检测过程中出现异常: {e}", "warning")
            # 重新抛出异常让上层处理
            raise
            
    async def _update_gift_card_status_in_db(self, gift_card_number: str, new_status: str):
        """更新数据库中的礼品卡状态"""
        try:
            import sqlite3
            import os
            
            # 数据库路径
            db_path = os.path.join(os.path.dirname(__file__), '..', 'database.db')
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # 更新礼品卡状态
                cursor.execute("""
                    UPDATE gift_cards 
                    SET status = ?, updated_at = datetime('now') 
                    WHERE gift_card_number = ?
                """, (new_status, gift_card_number))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    print(f"📝 数据库更新成功: {gift_card_number[:4]}**** -> {new_status}")
                else:
                    print(f"⚠️ 未找到礼品卡记录: {gift_card_number[:4]}****")
                    
        except Exception as e:
            print(f"❌ 数据库更新失败: {e}")

    async def _notify_gift_card_status_update(self, gift_card_number: str, new_status: str, message: str):
        """通知前端礼品卡状态更新"""
        import time

        try:
            # 发送WebSocket消息通知前端
            if hasattr(self, 'message_service') and self.message_service:
                self.message_service.publish('gift_card_status_update', {
                    'gift_card_number': gift_card_number,
                    'status': new_status,
                    'message': message,
                    'timestamp': time.time()
                })
                print(f"📡 已发送礼品卡状态更新通知: {gift_card_number[:4]}**** -> {new_status}")

            # 如果有WebSocket处理器，也发送更新
            from app import websocket_handler
            if websocket_handler:
                websocket_handler.broadcast('gift_card_status_update', {
                    'gift_card_number': gift_card_number,
                    'status': new_status,
                    'message': message,
                    'timestamp': time.time()
                })

        except Exception as e:
            print(f"❌ 发送礼品卡状态更新通知失败: {e}")

    # =============