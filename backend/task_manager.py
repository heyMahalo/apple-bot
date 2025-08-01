import threading
import json
import os
import sys
import asyncio
import platform
from typing import Dict, List, Optional
from datetime import datetime
import logging

# 使用默认事件循环策略以支持GUI应用程序
if platform.system() == 'Darwin':
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

from models.task import Task, TaskStatus, TaskStep, GiftCard
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

# 延迟导入Celery任务，避免循环导入
def get_celery_tasks():
    """延迟导入Celery任务"""
    try:
        from celery_tasks import execute_apple_task, cleanup_task, cancel_task
        return execute_apple_task, cleanup_task, cancel_task
    except ImportError as e:
        logger.warning(f"Celery任务导入失败，回退到线程模式: {e}")
        return None, None, None

class TaskManager:
    def __init__(self, max_workers: int = 3, use_celery: bool = True):
        self.tasks: Dict[str, Task] = {}
        self.max_workers = max_workers
        self.use_celery = use_celery
        self.running_tasks: Dict[str, asyncio.Task] = {}  # 线程模式的异步任务
        self.celery_tasks: Dict[str, AsyncResult] = {}    # Celery任务结果
        self._lock = threading.Lock()
        self.automation_service = None  # 自动化服务实例

        # 获取Celery任务函数
        self.execute_task_func, self.cleanup_task_func, self.cancel_task_func = get_celery_tasks()

        if self.use_celery and self.execute_task_func:
            logger.info("🚀 TaskManager使用Celery模式")
            # 🚀 启动时恢复任务状态
            self._restore_tasks_from_persistence()
        else:
            logger.info("🔄 TaskManager使用线程模式")
            self.use_celery = False
            # 线程模式也需要恢复任务状态
            self._restore_tasks_from_persistence()

    def _restore_tasks_from_persistence(self):
        """从数据库和Celery恢复任务状态"""
        try:
            logger.info("🔄 开始恢复任务状态...")

            # 从数据库恢复所有任务
            from models.database import DatabaseManager
            db_manager = DatabaseManager()
            db_tasks = db_manager.get_all_tasks()
            restored_count = 0

            for db_task in db_tasks:
                try:
                    # 重建Task对象
                    task = Task.from_dict(db_task)
                    self.tasks[task.id] = task
                    restored_count += 1

                    # 如果是Celery模式且任务状态为running，尝试恢复Celery任务引用
                    if self.use_celery and task.status == TaskStatus.RUNNING:
                        self._restore_celery_task_reference(task)

                except Exception as e:
                    logger.error(f"❌ 恢复任务失败: {db_task.get('id', 'unknown')} - {e}")

            logger.info(f"✅ 任务状态恢复完成: 共恢复 {restored_count} 个任务")

        except Exception as e:
            logger.error(f"❌ 任务状态恢复失败: {e}")

    def _restore_celery_task_reference(self, task: Task):
        """恢复Celery任务引用"""
        try:
            logger.debug(f"🔄 尝试恢复Celery任务引用: {task.id}")
            # 暂时跳过，因为我们需要存储Celery任务ID
        except Exception as e:
            logger.warning(f"⚠️ 无法恢复Celery任务引用: {task.id} - {e}")

    def _persist_task(self, task: Task):
        """持久化单个任务到数据库"""
        try:
            from models.database import DatabaseManager
            db_manager = DatabaseManager()
            db_manager.save_task(task.to_dict())
            logger.debug(f"💾 任务已持久化: {task.id}")
        except Exception as e:
            logger.error(f"❌ 任务持久化失败: {task.id} - {e}")

    def _update_task_status(self, task: Task, status: TaskStatus, persist: bool = True):
        """更新任务状态并可选择性持久化"""
        old_status = task.status
        task.status = status

        if persist:
            self._persist_task(task)

        logger.debug(f"🔄 任务状态更新: {task.id} {old_status} -> {status}")

    def set_automation_service(self, automation_service):
        """设置自动化服务实例"""
        self.automation_service = automation_service
        
    def create_task(self, task_config) -> Task:
        """创建新任务"""
        task = Task(
            id=None,  # 自动生成UUID
            config=task_config
        )
        
        with self._lock:
            self.tasks[task.id] = task

        # 🚀 持久化任务到数据库
        self._persist_task(task)

        logger.info(f"Created task {task.id}: {task.config.name}")
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        return self.tasks.get(task_id)

    async def continue_task_execution(self, task_id: str) -> bool:
        """继续执行等待中的任务"""
        try:
            task = self.get_task(task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            if task.status != TaskStatus.WAITING_GIFT_CARD_INPUT:
                logger.error(f"任务 {task_id} 状态不是等待礼品卡输入: {task.status}")
                return False

            # 恢复任务状态为运行中
            task.status = TaskStatus.RUNNING
            task.add_log("🔄 继续执行任务...", "info")

            # 继续执行后续步骤
            await self._continue_task_steps(task)

            return True

        except Exception as e:
            logger.error(f"继续执行任务失败: {str(e)}")
            return False

    async def _continue_task_steps(self, task: Task):
        """继续执行任务的后续步骤"""
        try:
            # 礼品卡应用完成后，继续到下一步
            task.add_log("🎯 礼品卡应用完成，继续后续步骤...", "info")
            logger.info(f"🔄 开始继续执行任务步骤: {task.id}")

            # 获取任务的礼品卡信息
            gift_card_numbers = []
            if task.config.gift_cards:
                gift_card_numbers = [gc.number for gc in task.config.gift_cards]
                logger.info(f"📋 从gift_cards获取到 {len(gift_card_numbers)} 张礼品卡")
            elif task.config.gift_card_code:  # 向后兼容
                gift_card_numbers = [task.config.gift_card_code]
                logger.info(f"📋 从gift_card_code获取到礼品卡: {task.config.gift_card_code[:4]}****")

            if not gift_card_numbers:
                task.add_log("⚠️ 没有找到礼品卡信息", "warning")
                logger.warning(f"❌ 任务 {task.id} 没有找到礼品卡信息")
                task.status = TaskStatus.FAILED
                return

            # 检查自动化服务
            logger.info(f"🔍 检查自动化服务: {self.automation_service is not None}")

            # 调用自动化服务继续执行礼品卡输入
            if self.automation_service:
                task.add_log(f"🚀 开始自动输入 {len(gift_card_numbers)} 张礼品卡", "info")
                logger.info(f"🚀 调用自动化服务继续执行礼品卡输入: {gift_card_numbers}")
                success = await self.automation_service.continue_with_gift_card_input(task, gift_card_numbers)
                logger.info(f"✅ 自动化服务执行结果: {success}")
                if not success:
                    task.add_log("❌ 继续执行礼品卡输入失败", "error")
                    task.status = TaskStatus.FAILED
            else:
                task.add_log("❌ 自动化服务不可用", "error")
                logger.error(f"❌ 任务 {task.id} 自动化服务不可用")
                task.status = TaskStatus.FAILED

        except Exception as e:
            task.add_log(f"❌ 继续执行任务步骤失败: {e}", "error")
            logger.error(f"❌ 继续执行任务步骤失败: {e}", exc_info=True)
            task.status = TaskStatus.FAILED

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_active_tasks(self) -> List[Task]:
        """获取活跃任务（运行中、等待中或各阶段状态）- 包含浏览器状态检查"""
        active_statuses = [
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.STAGE_1_PRODUCT_CONFIG,
            TaskStatus.STAGE_2_ACCOUNT_LOGIN,
            TaskStatus.STAGE_3_ADDRESS_PHONE,
            TaskStatus.STAGE_4_GIFT_CARD,
            TaskStatus.WAITING_GIFT_CARD_INPUT
        ]

        active_tasks = []
        for task in self.tasks.values():
            if task.status in active_statuses:
                # 对于PENDING状态的任务，不需要检查浏览器
                if task.status == TaskStatus.PENDING:
                    active_tasks.append(task)
                    continue

                # 对于其他活跃状态，检查是否有对应的浏览器页面或Celery任务
                has_browser_or_celery = self._is_task_truly_active(task)

                if has_browser_or_celery:
                    active_tasks.append(task)
                else:
                    # 如果没有浏览器页面也没有Celery任务，但任务状态是等待输入，则保持活跃
                    if task.status == TaskStatus.WAITING_GIFT_CARD_INPUT:
                        logger.debug(f"✅ 任务 {task.id[:8]} 正在等待礼品卡输入，保持活跃状态")
                        active_tasks.append(task)
                    else:
                        # 给任务一些宽容时间，避免过于严格的检查导致闪烁
                        logger.debug(f"⚠️ 任务 {task.id[:8]} 状态为 {task.status} 但没有活跃的执行实例")
                        # 暂时不标记为失败，让任务自然完成或失败
                        active_tasks.append(task)

        return active_tasks

    def _is_task_truly_active(self, task: Task) -> bool:
        """检查任务是否真正在运行（有浏览器页面或Celery任务）"""
        try:
            # 检查是否有Celery任务在运行
            if self.use_celery and task.id in self.celery_tasks:
                celery_result = self.celery_tasks[task.id]
                if celery_result and not celery_result.ready():
                    logger.debug(f"✅ 任务 {task.id[:8]} 有活跃的Celery任务")
                    return True
                else:
                    logger.debug(f"⚠️ 任务 {task.id[:8]} 的Celery任务已完成或不存在")

            # 检查是否有浏览器页面
            if self.automation_service:
                page = self.automation_service.pages.get(task.id)
                if page:
                    try:
                        # 尝试访问页面属性来验证页面是否有效
                        _ = page.url
                        logger.debug(f"✅ 任务 {task.id[:8]} 有活跃的浏览器页面")
                        return True
                    except Exception as e:
                        logger.debug(f"⚠️ 任务 {task.id[:8]} 的浏览器页面无效: {e}")
                else:
                    logger.debug(f"⚠️ 任务 {task.id[:8]} 没有浏览器页面")

            # 检查是否有异步任务在运行（线程模式）
            if not self.use_celery and task.id in self.running_tasks:
                async_task = self.running_tasks[task.id]
                if async_task and not async_task.done():
                    logger.debug(f"✅ 任务 {task.id[:8]} 有活跃的异步任务")
                    return True
                else:
                    logger.debug(f"⚠️ 任务 {task.id[:8]} 的异步任务已完成或不存在")

            return False

        except Exception as e:
            logger.debug(f"⚠️ 检查任务 {task.id[:8]} 活跃状态失败: {e}")
            return False

    def start_task(self, task_id: str, websocket_handler=None) -> bool:
        """启动任务"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return False
            
        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task {task_id} is not in pending status")
            return False
        
        # 检查并发限制 - 包含所有活跃状态
        active_statuses = [
            TaskStatus.RUNNING,
            TaskStatus.STAGE_1_PRODUCT_CONFIG,
            TaskStatus.STAGE_2_ACCOUNT_LOGIN,
            TaskStatus.STAGE_3_ADDRESS_PHONE,
            TaskStatus.STAGE_4_GIFT_CARD,
            TaskStatus.WAITING_GIFT_CARD_INPUT
        ]
        running_count = len([t for t in self.tasks.values() if t.status in active_statuses])
        if running_count >= self.max_workers:
            logger.warning(f"Maximum concurrent tasks ({self.max_workers}) reached")
            return False
        
        # 更新任务状态
        self._update_task_status(task, TaskStatus.RUNNING)
        task.started_at = datetime.now()
        task.add_log(f"任务开始执行")

        # 🚀 通过Redis发送状态更新（100%同步）
        try:
            from services.message_service import get_message_service
            message_service = get_message_service()
            message_service.sync_task_status(
                task_id=task.id,
                status=task.status.value,
                progress=task.progress,
                message="任务开始执行"
            )
            logger.info(f"✅ 任务状态已通过Redis同步: {task_id}")
        except Exception as e:
            logger.warning(f"⚠️ Redis同步失败，使用WebSocket: {e}")

        # 🚀 发送详细的状态更新事件
        if websocket_handler:
            # 发送任务状态更新事件
            websocket_handler.broadcast('task_status_update', {
                'task_id': task.id,
                'status': task.status.value,
                'progress': task.progress,
                'message': f"任务已启动"
            })
            # 向后兼容的通用更新事件
            websocket_handler.broadcast('task_update', task.to_dict())

        # 🚀 使用Celery或线程执行任务
        if self.use_celery and self.execute_task_func:
            success = self._start_task_celery(task, websocket_handler)
        else:
            success = self._start_task_async(task, websocket_handler)

        if success:
            logger.info(f"✅ 任务启动成功: {task_id} ({'Celery' if self.use_celery else '线程'}模式)")
            return True
        else:
            task.status = TaskStatus.FAILED
            task.add_log("启动任务进程失败", "error")
            return False

    def _start_task_celery(self, task: Task, websocket_handler=None) -> bool:
        """使用Celery启动任务"""
        try:
            # 将任务数据序列化
            task_data = task.to_dict()

            # 提交Celery任务
            celery_result = self.execute_task_func.delay(task_data)

            # 存储Celery任务结果
            self.celery_tasks[task.id] = celery_result

            logger.info(f"🚀 Celery任务已提交: {task.id} -> {celery_result.id}")
            task.add_log(f"Celery任务已提交: {celery_result.id}", "info")

            return True

        except Exception as e:
            logger.error(f"❌ Celery任务提交失败: {task.id} - {str(e)}")
            task.add_log(f"Celery任务提交失败: {str(e)}", "error")
            return Fal