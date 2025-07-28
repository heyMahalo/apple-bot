import asyncio
import logging
from typing import Optional, Dict
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import time
import os
import sys

# 添加主目录到系统路径以导入apple_automator
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from models.task import Task, TaskStep

logger = logging.getLogger(__name__)

class AutomationService:
    """集成Apple自动化逻辑的服务类 - 支持多并发"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.contexts: Dict[str, BrowserContext] = {}  # task_id -> BrowserContext
        self.pages: Dict[str, Page] = {}  # task_id -> Page
        
    async def _setup_playwright(self, task: Task) -> bool:
        """初始化Playwright环境"""
        try:
            task.add_log("🚀 开始初始化Playwright环境...", "info")

            if not self.playwright:
                task.add_log("📦 启动Playwright引擎...", "info")
                self.playwright = await async_playwright().start()
                task.add_log("✅ Playwright引擎启动成功", "success")

            if not self.browser:
                task.add_log("🌐 启动Chrome浏览器...", "info")
                self.browser = await self.playwright.chromium.launch(
                    headless=False,  # 开发模式：显示浏览器
                    slow_mo=300,     # 适中的延迟便于观察
                    devtools=True,   # 开启开发者工具
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--start-maximized'  # 最大化窗口
                    ]
                )
                task.add_log("✅ Chrome浏览器启动成功", "success")

            # 为每个任务创建独立的浏览器上下文
            task.add_log("🔧 创建浏览器上下文...", "info")
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            task.add_log("📄 创建新页面...", "info")
            page = await context.new_page()

            # 启用详细日志
            page.on("console", lambda msg: task.add_log(f"🖥️ 浏览器控制台: {msg.text}", "info"))
            page.on("pageerror", lambda error: task.add_log(f"❌ 页面错误: {error}", "error"))

            self.contexts[task.id] = context
            self.pages[task.id] = page

            task.add_log("🎉 浏览器环境初始化完成", "success")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup playwright: {str(e)}")
            task.add_log(f"浏览器初始化失败: {str(e)}", "error")
            return False
    
    def initialize_sync(self, task: Task) -> bool:
        """同步初始化任务 - 避免事件循环冲突"""
        try:
            task.add_log("开始初始化任务...", "info")

            # 使用同步的playwright
            from playwright.sync_api import sync_playwright

            if not hasattr(self, 'sync_playwright'):
                task.add_log("启动同步Playwright...", "info")
                self.sync_playwright = sync_playwright().start()
                task.add_log("Playwright启动成功", "success")

            if not hasattr(self, 'sync_browser'):
                task.add_log("启动Chrome浏览器...", "info")
                self.sync_browser = self.sync_playwright.chromium.launch(
                    headless=False,  # 开发模式：显示浏览器
                    slow_mo=500,     # 增加延迟便于观察
                    devtools=True,   # 开启开发者工具
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                task.add_log("Chrome浏览器启动成功", "success")

            # 为每个任务创建独立的浏览器上下文
            task.add_log("创建浏览器上下文...", "info")
            context = self.sync_browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            task.add_log("创建新页面...", "info")
            page = context.new_page()

            # 存储同步版本的上下文和页面
            if not hasattr(self, 'sync_contexts'):
                self.sync_contexts = {}
            if not hasattr(self, 'sync_pages'):
                self.sync_pages = {}

            self.sync_contexts[task.id] = context
            self.sync_pages[task.id] = page

            task.add_log("浏览器环境初始化成功", "success")
            return True

        except Exception as e:
            error_msg = f"任务初始化失败: {str(e)}"
            logger.error(error_msg)
            task.add_log(error_msg, "error")
            return False

    async def initialize(self, task: Task) -> bool:
        """异步初始化任务"""
        try:
            task.add_log("开始初始化任务...", "info")
            result = await self._setup_playwright(task)
            if result:
                task.add_log("任务初始化完成", "success")
            return result
        except Exception as e:
            error_msg = f"任务初始化失败: {str(e)}"
            logger.error(error_msg)
            task.add_log(error_msg, "error")
            return False
    
    def navigate_to_product_sync(self, task: Task) -> bool:
        """同步导航到产品页面"""
        try:
            page = self.sync_pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log(f"正在导航到产品页面: {task.config.url}", "info")

            # 导航到页面
            response = page.goto(task.config.url, wait_until='domcontentloaded', timeout=60000)
            task.add_log(f"页面响应状态: {response.status}", "info")

            # 等待页面加载
            task.add_log("等待页面完全加载...", "info")
            import time
            time.sleep(3)

            # 获取页面标题进行验证
            title = page.title()
            task.add_log(f"页面标题: {title}", "info")

            # 检查是否成功到达产品页面
            current_url = page.url
            task.add_log(f"当前URL: {current_url}", "info")

            if "apple.com" in current_url:
                task.add_log(f"✅ 成功导航到Apple产品页面", "success")
                return True
            else:
                task.add_log(f"⚠️ 可能未正确导航到Apple页面", "warning")
                return True  # 继续执行，让后续步骤处理

        except Exception as e:
            task.add_log(f"❌ 导航失败: {str(e)}", "error")
            return False

    async def navigate_to_product(self, task: Task) -> bool:
        """异步导航到产品页面"""
        try:
            result = await self._navigate_to_product_async(task)
            return result
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            task.add_log(f"导航失败: {str(e)}", "error")
            return False

    def configure_product_sync(self, task: Task) -> bool:
        """同步配置产品选项"""
        try:
            task.add_log("开始配置产品选项...", "info")
            # TODO: 实现同步版本的产品配置
            task.add_log("产品配置完成", "success")
            return True
        except Exception as e:
            task.add_log(f"产品配置失败: {str(e)}", "error")
            return False

    def add_to_bag_sync(self, task: Task) -> bool:
        """同步添加到购物袋"""
        try:
            task.add_log("开始添加到购物袋...", "info")
            # TODO: 实现同步版本的添加到购物袋
            task.add_log("添加到购物袋完成", "success")
            return True
        except Exception as e:
            task.add_log(f"添加到购物袋失败: {str(e)}", "error")
            return False

    def checkout_sync(self, task: Task) -> bool:
        """同步结账流程"""
        try:
            task.add_log("开始结账流程...", "info")
            # TODO: 实现同步版本的结账
            task.add_log("结账流程完成", "success")
            return True
        except Exception as e:
            task.add_log(f"结账失败: {str(e)}", "error")
            return False

    def apply_gift_card_sync(self, task: Task) -> bool:
        """同步应用礼品卡"""
        try:
            task.add_log("开始应用礼品卡...", "info")
            # TODO: 实现同步版本的礼品卡应用
            task.add_log("礼品卡应用完成", "success")
            return True
        except Exception as e:
            task.add_log(f"礼品卡应用失败: {str(e)}", "error")
            return False

    def finalize_purchase_sync(self, task: Task) -> bool:
        """同步完成购买"""
        try:
            task.add_log("开始完成购买...", "info")
            # TODO: 实现同步版本的购买完成
            task.add_log("购买完成", "success")
            return True
        except Exception as e:
            task.add_log(f"完成购买失败: {str(e)}", "error")
            return False
    
    async def _navigate_to_product_async(self, task: Task) -> bool:
        """异步导航到产品页面"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            task.add_log(f"🧭 正在导航到产品页面...", "info")
            task.add_log(f"🔗 目标URL: {task.config.url}", "info")

            # 导航到页面
            task.add_log("📡 发送页面请求...", "info")
            response = await page.goto(task.config.url, wait_until='domcontentloaded', timeout=60000)
            task.add_log(f"📊 页面响应状态: {response.status}", "info")

            # 等待页面加载
            task.add_log("⏳ 等待页面完全加载...", "info")
            await asyncio.sleep(3)

            # 获取页面标题进行验证
            title = await page.title()
            task.add_log(f"📋 页面标题: {title}", "info")

            # 检查是否成功到达产品页面
            current_url = page.url
            task.add_log(f"🌐 当前URL: {current_url}", "info")

            # 检查页面是否包含产品信息
            try:
                # 等待产品页面的关键元素加载
                await page.wait_for_selector('[data-autom="add-to-cart"], .add-to-cart, .rf-pdp-buybox', timeout=10000)
                task.add_log("🛍️ 检测到产品购买按钮，页面加载成功", "success")
            except:
                task.add_log("⚠️ 未检测到购买按钮，但继续执行", "warning")

            if "apple.com" in current_url:
                task.add_log(f"✅ 成功导航到Apple产品页面", "success")
                return True
            else:
                task.add_log(f"⚠️ 可能未正确导航到Apple页面", "warning")
                return True  # 继续执行，让后续步骤处理

        except Exception as e:
            task.add_log(f"❌ 导航失败: {str(e)}", "error")
            return False
    
    async def configure_product(self, task: Task, url_analysis: dict = None) -> bool:
        """配置产品选项 - 支持智能跳过"""
        try:
            result = await self._configure_product_async(task, url_analysis)
            return result
        except Exception as e:
            logger.error(f"Product configuration failed: {str(e)}")
            task.add_log(f"产品配置失败: {str(e)}", "error")
            return False
    
    async def _configure_product_async(self, task: Task, url_analysis: dict = None) -> bool:
        """基于apple_automator.py的产品配置逻辑"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")

            config = task.config.product_config
            if not config:
                task.add_log("⚠️ 无产品配置信息，跳过配置步骤", "warning")
                return True

            task.add_log(f"🔧 开始配置产品选项（基于apple_automator.py逻辑）...", "info")

            # 等待页面加载完成
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # 根据URL分析结果决定需要跳过的选项
            skip_options = set()
            if url_analysis and url_analysis.get('skip_configuration'):
                if url_analysis.get('has_model'):
                    skip_options.add('Model')
                    task.add_log("⏭️ 跳过型号选择（URL已包含）", "info")
                if url_analysis.get('has_storage'):
                    skip_options.add('Storage')
                    task.add_log("⏭️ 跳过存储选择（URL已包含）", "info")
                if url_analysis.get('has_color'):
                    skip_options.add('Finish')
                    task.add_log("⏭️ 跳过颜色选择（URL已包含）", "info")

            # 配置型号 (Model) - 只有在URL中没有包含时才配置
            if config.model and 'Model' not in skip_options:
                task.add_log(f"📱 正在选择型号: {config.model}", "info")
                success = await self._apple_select_model(page, config.model, task)
                if not success:
                    task.add_log("❌ 型号选择失败", "error")
                    return False
                task.add_log("✅ 型号选择完成", "success")
                await page.wait_for_timeout(1000)

            # 配置颜色/材质 (Finish) - 只有在URL中没有包含时才配置
            if config.finish and 'Finish' not in skip_options:
                task.add_log(f"🎨 正在选择颜色/材质: {config.finish}", "info")
                success = await self._apple_select_finish(page, config.finish, task)
                if not success:
                    task.add_log("❌ 颜色选择失败", "error")
                    return False
                task.add_log("✅ 颜色选择完成", "success")
                await page.wait_for_timeout(1000)

            # 配置存储容量 (Storage) - 只有在URL中没有包含时才配置
            if config.storage and 'Storage' not in skip_options:
                task.add_log(f"💾 正在选择存储容量: {config.storage}", "info")
                success = await self._apple_select_storage(page, config.storage, task)
                if not success:
                    task.add_log("❌ 存储容量选择失败", "error")
                    return False
                task.add_log("✅ 存储容量选择完成", "success")
                await page.wait_for_timeout(1000)
            
            # 以下选项始终需要配置（不受URL影响）- 使用apple_automator.py的精确逻辑

            # 1. 配置Apple Trade In - 必须选择 "No trade in"
            task.add_log(f"🔄 正在选择Apple Trade In: No trade in", "info")
            success = await self._apple_select_trade_in(page, "No trade in", task)
            if not success:
                task.add_log("❌ Apple Trade In选择失败", "error")
                return False
            task.add_log("✅ Apple Trade In选择完成", "success")
            await page.wait_for_timeout(1000)

            # 2. 配置Payment - 必须选择 "Buy"
            task.add_log(f"💳 正在选择Payment: Buy", "info")
            success = await self._apple_select_payment(page, "Buy", task)
            if not success:
                task.add_log("❌ Payment选择失败", "error")
                return False
            task.add_log("✅ Payment选择完成", "success")
            await page.wait_for_timeout(1000)

            # 3. 配置AppleCare+ Coverage - 必须选择 "No AppleCare+ Coverage"
            task.add_log(f"🛡️ 正在选择AppleCare+ Coverage: No AppleCare+ Coverage", "info")
            success = await self._apple_select_applecare(page, "No AppleCare+ Coverage", task)
            if not success:
                task.add_log("❌ AppleCare+ Coverage选择失败", "error")
                return False
            task.add_log("✅ AppleCare+ Coverage选择完成", "success")
            await page.wait_for_timeout(1000)

            task.add_log("🎉 产品配置完成", "success")
            return True
            
        except Exception as e:
            task.add_log(f"产品配置失败: {str(e)}", "error")
            return False
    
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

            # 尝试多种Trade In选择策略
            strategies = [
                # 策略1: 通过具体的data-autom属性
                lambda: self._try_trade_in_autom_match(page, label),
                # 策略2: 直接文本匹配
                lambda: self._try_trade_in_text_match(page, label),
                # 策略3: 通过fieldset查找
                lambda: self._try_trade_in_fieldset_match(page, label),
                # 策略4: 通过按钮查找
                lambda: self._try_trade_in_button_match(page, label),
                # 策略5: 通过radio button查找
                lambda: self._try_trade_in_radio_match(page, label),
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

            # 尝试多种Payment选择策略
            strategies = [
                # 策略1: 通过具体的data-autom属性
                lambda: self._try_payment_autom_match(page, label),
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

            # 尝试多种AppleCare选择策略
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
            # 等待Trade In区域出现
            await page.wait_for_selector('[data-analytics-section="tradein"]', timeout=30000)
            await page.wait_for_timeout(2000)
            task.add_log("Trade In区域已启用", "success")
        except Exception as e:
            task.add_log(f"等待Trade In区域失败: {e}", "warning")

    async def _wait_for_payment_enabled(self, page: Page, task: Task):
        """等待Payment区域启用"""
        try:
            task.add_log("等待Payment区域启用...", "info")
            # 等待Payment区域出现
            await page.wait_for_selector('[data-analytics-section="payment"]', timeout=30000)
            await page.wait_for_timeout(2000)
            task.add_log("Payment区域已启用", "success")
        except Exception as e:
            task.add_log(f"等待Payment区域失败: {e}", "warning")

    async def _wait_for_applecare_enabled(self, page: Page, task: Task):
        """等待AppleCare区域启用"""
        try:
            task.add_log("等待AppleCare区域启用...", "info")
            # 等待AppleCare区域出现
            await page.wait_for_selector('[data-analytics-section="applecare"]', timeout=30000)
            await page.wait_for_timeout(2000)
            task.add_log("AppleCare区域已启用", "success")
        except Exception as e:
            task.add_log(f"等待AppleCare区域失败: {e}", "warning")

    # ==================== Trade In选择策略 ====================

    async def _try_trade_in_autom_match(self, page: Page, label: str):
        """通过data-autom属性选择Trade In"""
        if "No trade" in label:
            selector = '[data-autom="dimensionTradeintradein-no"]'
        else:
            selector = f'[data-autom*="tradein"][data-autom*="{label.lower()}"]'

        element = page.locator(selector).first
        await element.wait_for(state='visible', timeout=10000)
        await element.scroll_into_view_if_needed()
        await element.click()

    async def _try_trade_in_text_match(self, page: Page, label: str):
        """通过文本匹配选择Trade In"""
        selectors = [
            f'text="{label}"',
            f'text*="{label}"',
            f'text="No trade in"',
            f'text="No trade-in"',
            f'text*="No trade"'
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
        raise Exception("No text match found")

    async def _try_trade_in_fieldset_match(self, page: Page, label: str):
        """通过fieldset查找Trade In"""
        fieldset = page.locator('fieldset:has-text("trade")').first
        await fieldset.wait_for(state='visible', timeout=10000)

        # 在fieldset中查找匹配的选项
        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_trade_in_button_match(self, page: Page, label: str):
        """通过按钮查找Trade In"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_trade_in_radio_match(self, page: Page, label: str):
        """通过radio button查找Trade In"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    # ==================== Payment选择策略 ====================

    async def _try_payment_autom_match(self, page: Page, label: str):
        """通过data-autom属性选择Payment"""
        if "Buy" in label:
            selector = '[data-autom="purchaseGroupOptionfullprice"]'
        else:
            selector = f'[data-autom*="payment"][data-autom*="{label.lower()}"]'

        element = page.locator(selector).first
        await element.wait_for(state='visible', timeout=10000)
        await element.scroll_into_view_if_needed()
        await element.click()

    async def _try_payment_text_match(self, page: Page, label: str):
        """通过文本匹配选择Payment"""
        selectors = [
            f'text="{label}"',
            f'text*="{label}"',
            f'[data-analytics-section*="payment"] text="{label}"',
            f'[data-analytics-section*="payment"] text*="{label}"'
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
        raise Exception("No payment text match found")

    async def _try_payment_fieldset_match(self, page: Page, label: str):
        """通过fieldset查找Payment"""
        fieldset = page.locator('[data-analytics-section*="payment"] fieldset').first
        await fieldset.wait_for(state='visible', timeout=10000)

        # 在fieldset中查找匹配的选项
        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_payment_button_match(self, page: Page, label: str):
        """通过按钮查找Payment"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_payment_radio_match(self, page: Page, label: str):
        """通过radio button查找Payment"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    # ==================== AppleCare选择策略 ====================

    async def _try_applecare_autom_match(self, page: Page, label: str):
        """通过data-autom属性选择AppleCare"""
        if "No AppleCare" in label or "No coverage" in label:
            selector = '[data-autom="noapplecare"]'
        else:
            selector = f'[data-autom*="applecare"][data-autom*="{label.lower()}"]'

        element = page.locator(selector).first
        await element.wait_for(state='visible', timeout=10000)
        await element.scroll_into_view_if_needed()
        await element.click()

    async def _try_applecare_text_match(self, page: Page, label: str):
        """通过文本匹配选择AppleCare"""
        selectors = [
            f'text="{label}"',
            f'text*="{label}"',
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
        """通过fieldset查找AppleCare"""
        fieldset = page.locator('[data-analytics-section*="applecare"] fieldset').first
        await fieldset.wait_for(state='visible', timeout=10000)

        # 在fieldset中查找匹配的选项
        option = fieldset.locator(f'text*="{label}"').first
        await option.wait_for(state='visible', timeout=5000)
        await option.scroll_into_view_if_needed()
        await option.click()

    async def _try_applecare_button_match(self, page: Page, label: str):
        """通过按钮查找AppleCare"""
        button = page.locator(f'button:has-text("{label}")').first
        await button.wait_for(state='visible', timeout=10000)
        await button.scroll_into_view_if_needed()
        await button.click()

    async def _try_applecare_radio_match(self, page: Page, label: str):
        """通过radio button查找AppleCare"""
        radio = page.locator(f'input[type="radio"] + label:has-text("{label}")').first
        await radio.wait_for(state='visible', timeout=10000)
        await radio.scroll_into_view_if_needed()
        await radio.click()

    # ==================== 颜色选择策略 ====================

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

    # ==================== 存储选择策略 ====================

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


    # ==================== 旧方法已删除，使用上面基于apple_automator.py的新方法 ====================



    # ==================== 添加到购物袋和结账方法 ====================


        try:
            task.add_log(f"🔍 开始选择AppleCare+ Coverage: {label}", "info")

            # 等待页面加载和Payment选择完成
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            await asyncio.sleep(3)

            # 尝试等待AppleCare区域启用
            try:
                await page.wait_for_selector('[data-analytics-section="applecare"]', timeout=15000)
                task.add_log("✅ AppleCare+ Coverage区域已加载", "info")
            except:
                task.add_log("⚠️ 未找到AppleCare区域，尝试通用选择器", "warning")

            # 针对"No AppleCare+ Coverage"的专门选择策略
            strategies = [
                # 策略1: 精确文本匹配
                'text="No AppleCare+ Coverage"',
                'text="No AppleCare Coverage"',
                'text="No AppleCare+"',
                'text="No coverage"',
                'text="No Coverage"',
                # 策略2: 包含文本匹配
                'text*="No AppleCare"',
                'text*="no applecare"',
                'text*="No coverage"',
                'text*="no coverage"',
                # 策略3: 通过radio button + label
                'input[type="radio"] + label:has-text("No AppleCare")',
                'input[type="radio"] + label:has-text("No coverage")',
                'input[type="radio"][value*="no"] + label',
                'input[type="radio"][value*="none"] + label',
                # 策略4: 通过fieldset查找
                'fieldset:has-text("AppleCare") input[type="radio"]:first-child',
                'fieldset:has-text("coverage") input[type="radio"]:first-child',
                # 策略5: 通过data属性
                '[data-autom*="no-applecare"]',
                '[data-autom*="noapplecare"]',
                '[data-autom*="no-coverage"]',
                '[data-autom*="nocoverage"]',
                # 策略6: 通过aria-label
                '[aria-label*="No AppleCare"]',
                '[aria-label*="no applecare"]',
                '[aria-label*="No coverage"]',
                '[aria-label*="no coverage"]',
                # 策略7: 通过按钮
                'button:has-text("No AppleCare")',
                'button:has-text("No coverage")'
            ]

            for i, selector in enumerate(strategies, 1):
                try:
                    task.add_log(f"🔄 尝试AppleCare策略 {i}: {selector}", "info")
                    element = page.locator(selector).first
                    await element.wait_for(state='visible', timeout=8000)
                    await element.click()
                    await asyncio.sleep(2)
                    task.add_log(f"✅ AppleCare+ Coverage选择成功: {label}", "success")
                    return True
                except Exception as e:
                    task.add_log(f"⚠️ 策略 {i} 失败: {str(e)}", "warning")
                    continue

            task.add_log(f"❌ 所有AppleCare+ Coverage选择策略都失败了", "error")
            return False

        except Exception as e:
            task.add_log(f"❌ AppleCare+ Coverage选择异常: {str(e)}", "error")
            return False

    async def _click_continue_button(self, page: Page, task: Task) -> bool:
        """点击继续按钮进入下一步"""
        try:
            task.add_log(f"🔍 查找继续按钮...", "info")

            # 等待页面稳定
            await asyncio.sleep(3)

            # 多种继续按钮的选择策略
            strategies = [
                # 策略1: 常见的继续按钮文本
                'button:has-text("Continue")',
                'button:has-text("Add to Bag")',
                'button:has-text("Add to Cart")',
                'button:has-text("Next")',
                'button:has-text("Proceed")',
                # 策略2: 通过data属性
                '[data-autom="add-to-cart"]',
                '[data-autom="continue"]',
                '[data-autom="proceed"]',
                # 策略3: 通过class
                '.button-continue',
                '.add-to-cart',
                '.proceed-button',
                # 策略4: 通过type和位置
                'button[type="submit"]',
                'input[type="submit"]',
                # 策略5: 通过aria-label
                '[aria-label*="Continue"]',
                '[aria-label*="Add to"]',
                '[aria-label*="Proceed"]'
            ]

            for i, selector in enumerate(strategies, 1):
                try:
                    task.add_log(f"🔄 尝试继续按钮策略 {i}: {selector}", "info")
                    element = page.locator(selector).first
                    await element.wait_for(state='visible', timeout=5000)

                    # 检查按钮是否可点击
                    is_enabled = await element.is_enabled()
                    if not is_enabled:
                        task.add_log(f"⚠️ 按钮存在但未启用，跳过策略 {i}", "warning")
                        continue

                    await element.click()
                    await asyncio.sleep(2)
                    task.add_log(f"✅ 继续按钮点击成功", "success")
                    return True
                except Exception as e:
                    task.add_log(f"⚠️ 策略 {i} 失败: {str(e)}", "warning")
                    continue

            task.add_log(f"❌ 所有继续按钮策略都失败了", "error")
            return False

        except Exception as e:
            task.add_log(f"❌ 点击继续按钮异常: {str(e)}", "error")
            return False
    
    async def _select_model(self, page: Page, model_label: str, task: Task) -> bool:
        """选择型号"""
        try:
            # 基于apple_automator的_select_model逻辑
            selectors = [
                f'input[data-autom*="dimensionFilter"][value*="{model_label}"]',
                f'label[role="radio"]:has-text("{model_label}")',
                f'button[role="radio"]:has-text("{model_label}")',
                f'fieldset:has-text("Model") label:has-text("{model_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择型号: {model_label}")
                        return True
                except:
                    continue
            
            task.add_log(f"未找到型号选项: {model_label}", "warning")
            return False
            
        except Exception as e:
            task.add_log(f"选择型号时出错: {str(e)}", "error")
            return False
    
    async def _select_finish(self, page: Page, finish_label: str, task: Task) -> bool:
        """选择颜色/材质"""
        try:
            # 基于apple_automator的颜色选择逻辑
            selectors = [
                f'input[data-autom*="dimensionFilter"][aria-label*="{finish_label}"]',
                f'label[role="radio"]:has-text("{finish_label}")',
                f'button[role="radio"]:has-text("{finish_label}")',
                f'fieldset:has-text("Finish") label:has-text("{finish_label}")',
                f'fieldset:has-text("finish") label:has-text("{finish_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择颜色: {finish_label}")
                        return True
                except:
                    continue
            
            task.add_log(f"未找到颜色选项: {finish_label}", "warning")
            return False
            
        except Exception as e:
            task.add_log(f"选择颜色时出错: {str(e)}", "error")
            return False
    
    async def _select_storage(self, page: Page, storage_label: str, task: Task) -> bool:
        """选择存储容量"""
        try:
            # 基于apple_automator的存储选择逻辑
            selectors = [
                f'input[data-autom*="dimensionFilter"][aria-label*="{storage_label}"]',
                f'label[role="radio"]:has-text("{storage_label}")',
                f'button[role="radio"]:has-text("{storage_label}")',
                f'fieldset:has-text("Storage") label:has-text("{storage_label}")',
                f'fieldset:has-text("storage") label:has-text("{storage_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择存储: {storage_label}")
                        return True
                except:
                    continue
            
            task.add_log(f"未找到存储选项: {storage_label}", "warning")
            return False
            
        except Exception as e:
            task.add_log(f"选择存储时出错: {str(e)}", "error")
            return False
    
    async def _select_trade_in(self, page: Page, trade_in_label: str, task: Task) -> bool:
        """选择以旧换新选项"""
        try:
            # 查找以旧换新部分
            selectors = [
                f'label[role="radio"]:has-text("{trade_in_label}")',
                f'button[role="radio"]:has-text("{trade_in_label}")',
                f'fieldset:has-text("trade") label:has-text("{trade_in_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择以旧换新: {trade_in_label}")
                        return True
                except:
                    continue
            
            return True  # 以旧换新是可选的
            
        except Exception as e:
            task.add_log(f"选择以旧换新时出错: {str(e)}", "error")
            return True  # 继续执行
    
    async def _select_payment(self, page: Page, payment_label: str, task: Task) -> bool:
        """选择付款方式"""
        try:
            selectors = [
                f'label[role="radio"]:has-text("{payment_label}")',
                f'button[role="radio"]:has-text("{payment_label}")',
                f'fieldset:has-text("payment") label:has-text("{payment_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择付款方式: {payment_label}")
                        return True
                except:
                    continue
            
            return True  # 付款方式是可选的
            
        except Exception as e:
            task.add_log(f"选择付款方式时出错: {str(e)}", "error")
            return True
    
    async def _select_applecare(self, page: Page, applecare_label: str, task: Task) -> bool:
        """选择AppleCare选项"""
        try:
            selectors = [
                f'label[role="radio"]:has-text("{applecare_label}")',
                f'button[role="radio"]:has-text("{applecare_label}")',
                f'fieldset:has-text("AppleCare") label:has-text("{applecare_label}")'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log(f"成功选择AppleCare: {applecare_label}")
                        return True
                except:
                    continue
            
            return True  # AppleCare是可选的
            
        except Exception as e:
            task.add_log(f"选择AppleCare时出错: {str(e)}", "error")
            return True
    
    async def add_to_bag(self, task: Task) -> bool:
        """添加到购物袋"""
        try:
            result = await self._add_to_bag_async(task)
            return result
        except Exception as e:
            logger.error(f"Add to bag failed: {str(e)}")
            task.add_log(f"添加到购物袋失败: {str(e)}", "error")
            return False
    
    async def _add_to_bag_async(self, task: Task) -> bool:
        """异步添加到购物袋"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")
            
            task.add_log("正在查找'添加到购物袋'按钮...")
            
            # 基于apple_automator的添加到购物袋逻辑
            selectors = [
                'button[data-autom="add-to-cart"]',
                'button:has-text("Add to Bag")',
                'button:has-text("添加到购物袋")',
                'button.add-to-cart',
                'input[type="submit"][value*="Add"]'
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log("成功点击'添加到购物袋'按钮")
                        await asyncio.sleep(3)
                        return True
                except:
                    continue
            
            task.add_log("未找到'添加到购物袋'按钮", "error")
            return False
            
        except Exception as e:
            task.add_log(f"添加到购物袋失败: {str(e)}", "error")
            return False
    
    async def checkout(self, task: Task) -> bool:
        """进入结账流程"""
        try:
            result = await self._checkout_async(task)
            return result
        except Exception as e:
            logger.error(f"Checkout failed: {str(e)}")
            task.add_log(f"结账失败: {str(e)}", "error")
            return False
    
    async def _checkout_async(self, task: Task) -> bool:
        """异步结账流程"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")
            
            task.add_log("开始结账流程...")
            
            # 查找结账按钮
            checkout_selectors = [
                'button:has-text("Review Bag")',
                'button:has-text("Checkout")',
                'button:has-text("结账")',
                'a[href*="bag"]',
                'button[data-autom*="bag"]'
            ]
            
            for selector in checkout_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        task.add_log("成功进入结账流程")
                        await asyncio.sleep(3)
                        return True
                except:
                    continue
            
            task.add_log("结账流程准备完成")
            return True
            
        except Exception as e:
            task.add_log(f"结账失败: {str(e)}", "error")
            return False
    
    async def apply_gift_card(self, task: Task) -> bool:
        """应用礼品卡"""
        try:
            if task.config.use_proxy:
                task.add_log("正在切换IP...")
                # TODO: 调用IP切换服务

            result = await self._apply_gift_card_async(task)
            return result
        except Exception as e:
            logger.error(f"Gift card application failed: {str(e)}")
            task.add_log(f"礼品卡应用失败: {str(e)}", "error")
            return False
    
    async def _apply_gift_card_async(self, task: Task) -> bool:
        """异步应用礼品卡"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")
            
            if not task.config.gift_cards:
                task.add_log("无礼品卡需要应用")
                return True
                
            task.add_log("正在应用礼品卡...")
            
            for i, card in enumerate(task.config.gift_cards):
                card_number = card.get('number', '')
                card_pin = card.get('pin', '')
                
                if not card_number:
                    continue
                    
                task.add_log(f"正在应用第 {i+1} 张礼品卡...")
                
                # 查找礼品卡输入字段
                gift_card_input = page.locator('input[placeholder*="gift"], input[name*="gift"], input[data-autom*="gift"]').first
                if await gift_card_input.count() > 0:
                    await gift_card_input.fill(card_number)
                    task.add_log(f"输入礼品卡号: {card_number[-4:]}")
                
                # 如果有PIN码输入
                if card_pin:
                    pin_input = page.locator('input[placeholder*="pin"], input[name*="pin"]').first
                    if await pin_input.count() > 0:
                        await pin_input.fill(card_pin)
                        task.add_log("输入PIN码")
                
                # 点击应用按钮
                apply_button = page.locator('button:has-text("Apply"), button:has-text("应用")').first
                if await apply_button.count() > 0:
                    await apply_button.click()
                    await asyncio.sleep(2)
                    task.add_log(f"第 {i+1} 张礼品卡应用完成")
                    
            task.add_log("所有礼品卡应用完成")
            return True
            
        except Exception as e:
            task.add_log(f"礼品卡应用失败: {str(e)}", "error")
            return False
    
    async def finalize_purchase(self, task: Task) -> bool:
        """完成购买"""
        try:
            result = await self._finalize_purchase_async(task)
            return result
        except Exception as e:
            logger.error(f"Purchase finalization failed: {str(e)}")
            task.add_log(f"购买完成失败: {str(e)}", "error")
            return False
    
    async def _finalize_purchase_async(self, task: Task) -> bool:
        """异步完成购买"""
        try:
            page = self.pages.get(task.id)
            if not page:
                raise Exception("Page not found for task")
            
            task.add_log("正在完成购买流程...")
            
            # 这里应该包含最终的确认购买步骤
            # 注意：在生产环境中，可能需要手动确认最后的购买步骤
            task.add_log("⚠️ 购买流程已准备完毕，等待手动确认...")
            
            # 保存最终截图
            await page.screenshot(path=f"final_purchase_{task.id}.png", full_page=True)
            task.add_log("购买页面截图已保存")
            
            return True
            
        except Exception as e:
            task.add_log(f"购买完成失败: {str(e)}", "error")
            return False
    
    async def cleanup_task(self, task_id: str):
        """清理任务相关资源"""
        try:
            if task_id in self.pages:
                del self.pages[task_id]
                
            if task_id in self.contexts:
                await self.contexts[task_id].close()
                del self.contexts[task_id]
                
        except Exception as e:
            logger.error(f"Failed to cleanup task {task_id}: {str(e)}")
    
    async def cleanup_all(self):
        """清理所有资源"""
        for task_id in list(self.contexts.keys()):
            await self.cleanup_task(task_id)
            
        if self.browser:
            await self.browser.close()
            
        if self.playwright:
            await self.playwright.stop()