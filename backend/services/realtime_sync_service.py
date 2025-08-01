import asyncio
import logging
import time
import threading
import platform
from typing import Dict, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class RealtimeSyncService:
    """SOTA实时同步服务 - 超高频率状态同步"""
    
    def __init__(self, socketio=None):
        self.socketio = socketio
        self.sync_queue = None  # 延迟初始化
        self.subscribers: Dict[str, list] = {}
        self.is_running = False
        self.sync_thread = None
        self.sync_interval = 0.1  # 100ms超高频率同步
        
        # 🚀 解决macOS事件循环问题
        if platform.system() == 'Darwin':
            # 设置事件循环策略
            try:
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            except Exception as e:
                logger.warning(f"设置事件循环策略失败: {e}")
        
    def start(self):
        """启动实时同步服务"""
        if self.is_running:
            return
            
        self.is_running = True
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        logger.info("🚀 SOTA实时同步服务已启动 - 100ms高频率同步")
    
    def stop(self):
        """停止实时同步服务"""
        self.is_running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=1)
    
    def _sync_loop(self):
        """同步循环 - 超高频率处理"""
        while self.is_running:
            try:
                # 创建新的事件循环（避免GUI显示问题）
                loop = asyncio.new_event_loop()
                
                asyncio.set_event_loop(loop)
                
                # 初始化队列（在正确的事件循环中）
                if self.sync_queue is None:
                    self.sync_queue = asyncio.Queue()
                
                # 运行同步任务
                loop.run_until_complete(self._process_sync_queue())
                loop.close()
                
                # 高频率休眠
                time.sleep(self.sync_interval)
                
            except Exception as e:
                logger.error(f"❌ 同步循环异常: {e}")
                time.sleep(0.5)
    
    async def _process_sync_queue(self):
        """处理同步队列"""
        try:
            # 批量处理队列中的所有消息
            messages = []
            try:
                while not self.sync_queue.empty():
                    message = self.sync_queue.get_nowait()
                    messages.append(message)
            except asyncio.QueueEmpty:
                pass
            
            # 批量发送消息
            for message in messages:
                await self._send_message(message)
                
        except Exception as e:
            logger.error(f"❌ 处理同步队列失败: {e}")
    
    async def _send_message(self, message):
        """发送消息"""
        try:
            event_name = message.get('event')
            data = message.get('data', {})
            
            # 立即WebSocket广播
            if self.socketio:
                self.socketio.emit(event_name, data)
            
            # 通知订阅者
            if event_name in self.subscribers:
                for callback in self.subscribers[event_name]:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"❌ 订阅者回调失败: {e}")
                        
        except Exception as e:
            logger.error(f"❌ 发送消息失败: {e}")
    
    def publish_sync(self, event: str, data: dict):
        """发布同步消息 - 线程安全版本"""
        try:
            message = {
                'event': event,
                'data': {
                    **data,
                    'timestamp': time.time(),
                    'sync_id': f"{event}_{int(time.time() * 1000)}"
                }
            }
            
            # 🚀 线程安全的消息发布
            if self.sync_queue is not None:
                # 使用线程安全的方式添加到队列
                def add_to_queue():
                    try:
                        # 创建临时事件循环来处理队列操作（避免GUI显示问题）
                        temp_loop = asyncio.new_event_loop()
                        
                        asyncio.set_event_loop(temp_loop)
                        temp_loop.run_until_complete(self.sync_queue.put(message))
                        temp_loop.close()
                    except Exception as e:
                        logger.error(f"❌ 添加消息到队列失败: {e}")
                        # 直接WebSocket发送作为备用
                        if self.socketio:
                            self.socketio.emit(event, data)
                
                # 在后台线程中执行
                threading.Thread(target=add_to_queue, daemon=True).start()
            else:
                # 如果队列未初始化，直接WebSocket发送
                if self.socketio:
                    self.socketio.emit(event, data)
                        
        except Exception as e:
            logger.error(f"❌ 发布同步消息失败: {e}")
            # 直接WebSocket发送作为备用
            if self.socketio:
                self.socketio.emit(event, data)
    
    def subscribe(self, event: str, callback: Callable):
        """订阅事件"""
        if event not in self.subscribers:
            self.subscribers[event] = []
        self.subscribers[event].append(callback)
    
    def publish_task_status(self, task_id: str, status: str, progress: float = None, message: str = ""):
        """发布任务状态更新 - 高优先级"""
        self.publish_sync('task_status_update', {
            'task_id': task_id,
            'status': status,
            'progress': progress,
            'message': message,
            'priority': 'high'
        })
    
    def publish_step_update(self, task_id: str, step: str, status: str, progress: float = None, message: str = ""):
        """发布步骤更新 - 高优先级"""
        self.publish_sync('step_update', {
            'task_id': task_id,
            'step': step,
            'status': status,
            'progress': progress,
            'message': message,
            'priority': 'high'
        })
    
    def publish_gift_card_required(self, task_id: str, message: str = "", url: str = ""):
        """发布礼品卡输入请求 - 最高优先级"""
        self.publish_sync('gift_card_input_required', {
            'task_id': task_id,
            'message': message,
            'url': url,
            'priority': 'critical'
        })

# 全局实例
_realtime_service = None

def get_realtime_sync_service():
    """获取实时同步服务实例"""
    global _realtime_service
    return _realtime_service

def init_realtime_sync_service(socketio=None):
    """初始化实时同步服务"""
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimeSyncService(socketio)
        _realtime_service.start()
    return _realtime_service