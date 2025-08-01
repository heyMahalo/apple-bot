import redis
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

logger = logging.getLogger(__name__)

class MessageService:
    """基于Redis的消息服务 - 100%实时同步解决方案"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis_client = None
        self.pubsub = None
        self.subscribers: Dict[str, Callable] = {}
        self.running = False
        self.listener_thread = None
        self.socketio = None  # SocketIO实例引用

        # 全局SocketIO实例引用
        self._global_socketio = None

    def set_socketio(self, socketio):
        """设置SocketIO实例"""
        self.socketio = socketio
        self._global_socketio = socketio  # 同时设置全局引用

    def connect(self, timeout=2):
        """连接Redis - 优化启动速度"""
        try:
            # 🚀 设置连接超时，避免启动时长时间等待
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=timeout,
                socket_timeout=timeout
            )
            # 快速测试连接
            self.redis_client.ping()
            logger.info("Redis连接成功")
            return True
        except Exception as e:
            logger.warning(f"Redis连接失败: {e}")
            # 如果Redis不可用，使用内存模拟
            self._use_memory_fallback()
            return False
    
    def _use_memory_fallback(self):
        """Redis不可用时的内存回退方案"""
        logger.warning("使用内存回退方案，进程间通信将受限")
        self._memory_store = {}
        self._memory_subscribers = {}
    
    def publish(self, channel: str, message: Dict[str, Any]):
        """发布消息"""
        try:
            if self.redis_client:
                message_str = json.dumps(message)
                self.redis_client.publish(channel, message_str)
                logger.info(f"发布消息到 {channel}")
            else:
                self._memory_publish(channel, message)
        except Exception as e:
            logger.error(f"发布消息失败: {e}")
    
    def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]):
        """订阅消息"""
        self.subscribers[channel] = callback
        logger.info(f"📝 注册订阅: {channel}")

        # 如果Redis可用且监听器正在运行，动态添加订阅
        if self.redis_client and self.running and self.pubsub:
            try:
                self.pubsub.subscribe(channel)
                logger.info(f"✅ 动态添加Redis订阅: {channel}")
            except Exception as e:
                logger.error(f"❌ 动态添加订阅失败: {e}")
        elif self.redis_client and not self.running:
            self._start_listener()
    
    def _start_listener(self):
        """启动消息监听器"""
        if self.running:
            return
            
        try:
            self.pubsub = self.redis_client.pubsub()
            for channel in self.subscribers.keys():
                self.pubsub.subscribe(channel)
            
            self.running = True
            self.listener_thread = threading.Thread(target=self._listen_messages, daemon=True)
            self.listener_thread.start()
            logger.info("消息监听器已启动")
        except Exception as e:
            logger.error(f"启动消息监听器失败: {e}")
    
    def _listen_messages(self):
        """监听消息"""
        while self.running:
            try:
                message = self.pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    channel = message['channel'].decode() if isinstance(message['channel'], bytes) else message['channel']
                    data = json.loads(message['data'])

                    logger.info(f"🔔 Redis收到消息: {channel} -> {data}")

                    if channel in self.subscribers:
                        try:
                            logger.info(f"📤 转发消息到回调: {channel}")
                            self.subscribers[channel](data)
                        except Exception as e:
                            logger.error(f"❌ 处理消息回调失败: {e}")
                    else:
                        logger.warning(f"⚠️ 没有找到频道的订阅者: {channel}")
            except Exception as e:
                logger.error(f"监听消息失败: {e}")
                time.sleep(1)
    
    def _memory_publish(self, channel: str, message: Dict[str, Any]):
        """内存回退的发布方法"""
        if channel in self._memory_subscribers:
            for callback in self._memory_subscribers[channel]:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(f"内存回调失败: {e}")
    
    def set_data(self, key: str, value: Any, expire: Optional[int] = None):
        """设置数据"""
        try:
            if self.redis_client:
                value_str = json.dumps(value)
                if expire:
                    self.redis_client.setex(key, expire, value_str)
                else:
                    self.redis_client.set(key, value_str)
            else:
                self._memory_store[key] = value
        except Exception as e:
            logger.error(f"设置数据失败: {e}")
    
    def get_data(self, key: str) -> Any:
        """获取数据"""
        try:
            if self.redis_client:
                value_str = self.redis_client.get(key)
                if value_str:
                    return json.loads(value_str)
            else:
                return self._memory_store.get(key)
        except Exception as e:
            logger.error(f"获取数据失败: {e}")
        return None
    
    def delete_data(self, key: str):
        """删除数据"""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            else:
                self._memory_store.pop(key, None)
        except Exception as e:
            logger.error(f"删除数据失败: {e}")
    
    def close(self):
        """关闭连接"""
        self.running = False
        if self.pubsub:
            self.pubsub.close()
        if self.redis_client:
            self.redis_client.close()
        logger.info("消息服务已关闭")

    def sync_task_status(self, task_id: str, status: str, progress: float = None, message: str = None):
        """同步任务状态到前端"""
        data = {
            'task_id': task_id,
            'status': status,
            'timestamp': time.time()
        }
        if progress is not None:
            data['progress'] = progress
        if message:
            data['message'] = message

        # 发布到Redis并立即转发
        self.publish('task_status_update', data)

        # 额外保障：直接设置到Redis存储
        self.set_data(f'task_status:{task_id}', data, expire=3600)

    def sync_task_log(self, task_id: str, level: str, message: str):
        """同步任务日志到前端"""
        data = {
            'task_id': task_id,
            'level': level,
            'message': message,
            'timestamp': time.time()
        }

        # 发布到Redis并立即转发
        self.publish('task_log', data)

# 全局消息服务实例
_message_service = None

def get_message_service() -> MessageService:
    """获取全局消息服务实例"""
    global _message_service
    if _message_service is None:
        _message_service = MessageService()
        _message_service.connect()
    return _message_service

def init_message_service(redis_url: str = "redis://localhost:6379/0"):
    """初始化消息服务"""
    global _message_service
    _message_service = MessageService(redis_url)
    _message_service.connect()
    return _message_service
