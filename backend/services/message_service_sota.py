"""
SOTA Redis消息服务 - Redis Stream + Hash持久化
实现任务生命周期管理、事件流、交互式输入等功能
"""

import redis
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

logger = logging.getLogger(__name__)

class SOTAMessageService:
    """SOTA Redis消息服务 - Redis Stream + Hash持久化"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis_client = None
        self.running = False
        
        # Redis键前缀
        self.TASK_HASH_PREFIX = "task:"
        self.TASK_STREAM_PREFIX = "tasks:"
        self.BROADCAST_STREAM = "tasks:broadcast"
        self.INPUT_QUEUE_PREFIX = "tasks:"
        
        # 事件保留策略
        self.STREAM_MAX_LEN = 10000  # 每个任务流最多保留10k条
        self.TASK_TTL = 7 * 24 * 3600  # 任务数据保留7天
        
        # 连接Redis
        self._connect_redis()
    
    def _connect_redis(self, timeout=2):
        """连接Redis - 优化启动速度"""
        try:
            # 🚀 设置连接超时，避免启动时长时间等待
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=timeout,
                socket_timeout=timeout
            )
            self.redis_client.ping()
            logger.info("✅ SOTA Redis连接成功")
            return True
        except Exception as e:
            logger.warning(f"❌ SOTA Redis连接失败: {e}")
            self.redis_client = None
            return False
    
    def create_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """创建任务 - 写入Hash并发送初始事件"""
        try:
            if not self.redis_client:
                return False
            
            # 写入任务Hash
            task_key = f"{self.TASK_HASH_PREFIX}{task_id}"
            task_data.update({
                'id': task_id,
                'status': 'pending',
                'progress': 0,
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            })
            
            self.redis_client.hset(task_key, mapping=task_data)
            self.redis_client.expire(task_key, self.TASK_TTL)
            
            # 发送创建事件
            self._send_event(task_id, 'task_created', {
                'task_id': task_id,
                'status': 'pending',
                'progress': 0,
                'message': '任务已创建'
            })
            
            logger.info(f"✅ 任务创建成功: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 创建任务失败: {e}")
            return False
    
    def sync_task_status(self, task_id: str, status: str, progress: float = None, message: str = ""):
        """同步任务状态 - 更新Hash并发送事件"""
        try:
            if not self.redis_client:
                return
            
            # 更新任务Hash
            task_key = f"{self.TASK_HASH_PREFIX}{task_id}"
            update_data = {
                'status': status,
                'last_updated': datetime.now().isoformat()
            }
            
            if progress is not None:
                update_data['progress'] = progress
            
            if message:
                update_data['last_message'] = message
            
            self.redis_client.hset(task_key, mapping=update_data)
            
            # 发送状态更新事件
            event_data = {
                'task_id': task_id,
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
            
            if progress is not None:
                event_data['progress'] = progress
            if message:
                event_data['message'] = message
            
            self._send_event(task_id, 'task_status_update', event_data)
            
        except Exception as e:
            logger.error(f"❌ 同步任务状态失败: {e}")
    
    def sync_task_log(self, task_id: str, level: str, message: str):
        """同步任务日志 - 发送日志事件"""
        try:
            if not self.redis_client:
                return
            
            log_data = {
                'task_id': task_id,
                'level': level,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
            
            self._send_event(task_id, 'task_log', log_data)
            
        except Exception as e:
            logger.error(f"❌ 同步任务日志失败: {e}")
    
    def send_step_update(self, task_id: str, step: str, status: str, progress: float = None, message: str = ""):
        """发送步骤更新事件"""
        try:
            if not self.redis_client:
                return
            
            # 更新任务Hash中的当前步骤
            task_key = f"{self.TASK_HASH_PREFIX}{task_id}"
            update_data = {
                'current_step': step,
                'last_updated': datetime.now().isoformat()
            }
            
            if progress is not None:
                update_data['progress'] = progress
            
            self.redis_client.hset(task_key, mapping=update_data)
            
            # 发送步骤更新事件
            event_data = {
                'task_id': task_id,
                'step': step,
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
            
            if progress is not None:
                event_data['progress'] = progress
            if message:
                event_data['message'] = message
            
            self._send_event(task_id, 'step_update', event_data)
            
        except Exception as e:
            logger.error(f"❌ 发送步骤更新失败: {e}")
    
    def publish_prompt(self, task_id: str, prompt_type: str, fields: List[Dict[str, Any]], message: str = ""):
        """发布交互式提示事件"""
        try:
            if not self.redis_client:
                return
            
            prompt_data = {
                'task_id': task_id,
                'prompt_type': prompt_type,
                'fields': fields,
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'prompt_id': str(uuid.uuid4())
            }
            
            self._send_event(task_id, 'prompt_required', prompt_data)
            
            # 同时更新任务状态为等待输入
            self.sync_task_status(task_id, 'waiting_input', message=f"等待用户输入: {message}")
            
            logger.info(f"✅ 发布提示事件: {task_id} - {prompt_type}")
            
        except Exception as e:
            logger.error(f"❌ 发布提示事件失败: {e}")
    
    def wait_for_input(self, task_id: str, timeout: int = 300) -> Optional[Dict[str, Any]]:
        """等待用户输入 - 阻塞式等待"""
        try:
            if not self.redis_client:
                return None
            
            input_key = f"{self.INPUT_QUEUE_PREFIX}{task_id}:input"
            
            # 使用BRPOP阻塞等待输入
            result = self.redis_client.brpop(input_key, timeout=timeout)
            
            if result:
                _, input_data = result
                return json.loads(input_data)
            else:
                logger.warning(f"⏰ 等待用户输入超时: {task_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 等待用户输入失败: {e}")
            return None
    
    def submit_input(self, task_id: str, input_data: Dict[str, Any]) -> bool:
        """提交用户输入"""
        try:
            if not self.redis_client:
                return False
            
            input_key = f"{self.INPUT_QUEUE_PREFIX}{task_id}:input"
            self.redis_client.lpush(input_key, json.dumps(input_data))
            
            # 发送输入提交事件
            self._send_event(task_id, 'input_submitted', {
                'task_id': task_id,
                'input_data': input_data,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"✅ 用户输入已提交: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 提交用户输入失败: {e}")
            return False
    
    def get_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务快照"""
        try:
            if not self.redis_client:
                return None
            
            task_key = f"{self.TASK_HASH_PREFIX}{task_id}"
            task_data = self.redis_client.hgetall(task_key)
            
            if task_data:
                return task_data
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取任务快照失败: {e}")
            return None
    
    def get_task_events(self, task_id: str, count: int = 50, start_id: str = "-") -> List[Dict[str, Any]]:
        """获取任务事件流"""
        try:
            if not self.redis_client:
                return []
            
            stream_key = f"{self.TASK_STREAM_PREFIX}{task_id}:events"
            
            # 从指定位置读取事件
            events = self.redis_client.xrevrange(stream_key, count=count, start="+", end=start_id)
            
            result = []
            for event_id, fields in events:
                event_data = dict(fields)
                event_data['event_id'] = event_id
                result.append(event_data)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取任务事件失败: {e}")
            return []
    
    def _send_event(self, task_id: str, event_type: str, event_data: Dict[str, Any]):
        """发送事件到Redis Stream"""
        try:
            if not self.redis_client:
                return
            
            # 添加事件元数据
            event_data.update({
                'event_type': event_type,
                'task_id': task_id,
                'timestamp': datetime.now().isoformat()
            })
            
            # 写入任务专用流
            task_stream = f"{self.TASK_STREAM_PREFIX}{task_id}:events"
            self.redis_client.xadd(task_stream, event_data, maxlen=self.STREAM_MAX_LEN)
            
            # 写入广播流（供Socket.IO网关消费）
            self.redis_client.xadd(self.BROADCAST_STREAM, event_data, maxlen=self.STREAM_MAX_LEN)
            
        except Exception as e:
            logger.error(f"❌ 发送事件失败: {e}")
    
    def cleanup_task(self, task_id: str):
        """清理任务数据"""
        try:
            if not self.redis_client:
                return
            
            # 删除任务Hash
            task_key = f"{self.TASK_HASH_PREFIX}{task_id}"
            self.redis_client.delete(task_key)
            
            # 删除任务流
            stream_key = f"{self.TASK_STREAM_PREFIX}{task_id}:events"
            self.redis_client.delete(stream_key)
            
            # 删除输入队列
            input_key = f"{self.INPUT_QUEUE_PREFIX}{task_id}:input"
            self.redis_client.delete(input_key)
            
            logger.info(f"✅ 任务数据已清理: {task_id}")
            
        except Exception as e:
            logger.error(f"❌ 清理任务数据失败: {e}")

# 全局实例
_sota_message_service = None

def init_sota_message_service(redis_url: str = "redis://localhost:6379/0") -> SOTAMessageService:
    """初始化SOTA消息服务"""
    global _sota_message_service
    _sota_message_service = SOTAMessageService(redis_url)
    return _sota_message_service

def get_sota_message_service() -> SOTAMessageService:
    """获取SOTA消息服务实例"""
    global _sota_message_service
    if _sota_message_service is None:
        _sota_message_service = SOTAMessageService()
    return _sota_message_service
