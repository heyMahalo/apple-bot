"""
Socket.IO网关服务 - 订阅Redis Stream并转发到前端
支持房间管理、断线重连、事件去重等功能
"""

import redis
import json
import logging
import threading
import time
from typing import Dict, Any, Set
from flask_socketio import SocketIO, emit, join_room, leave_room

logger = logging.getLogger(__name__)

class SocketIOGateway:
    """Socket.IO网关 - Redis Stream到WebSocket的桥梁"""
    
    def __init__(self, socketio: SocketIO, redis_url: str = "redis://localhost:6379/0"):
        self.socketio = socketio
        self.redis_url = redis_url
        self.redis_client = None
        self.running = False
        self.forwarder_thread = None
        
        # 客户端管理
        self.client_rooms: Dict[str, Set[str]] = {}  # client_id -> {task_ids}
        self.room_clients: Dict[str, Set[str]] = {}  # task_id -> {client_ids}
        
        # 事件去重
        self.last_event_ids: Dict[str, str] = {}  # client_id -> last_event_id
        
        # Redis Stream配置
        self.BROADCAST_STREAM = "tasks:broadcast"
        self.CONSUMER_GROUP = "socketio_gateway"
        self.CONSUMER_NAME = f"gateway_{int(time.time())}"
        
        # 连接Redis
        self._connect_redis()
        self._setup_consumer_group()
        
        # 设置Socket.IO事件处理
        self._setup_socketio_handlers()
    
    def _connect_redis(self):
        """连接Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("✅ Socket.IO网关Redis连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ Socket.IO网关Redis连接失败: {e}")
            self.redis_client = None
            return False
    
    def _setup_consumer_group(self):
        """设置Redis Stream消费组"""
        try:
            if not self.redis_client:
                return
            
            # 创建消费组（如果不存在）
            try:
                self.redis_client.xgroup_create(
                    self.BROADCAST_STREAM, 
                    self.CONSUMER_GROUP, 
                    id='0', 
                    mkstream=True
                )
                logger.info(f"✅ 创建消费组: {self.CONSUMER_GROUP}")
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"✅ 消费组已存在: {self.CONSUMER_GROUP}")
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ 设置消费组失败: {e}")
    
    def _setup_socketio_handlers(self):
        """设置Socket.IO事件处理器"""
        
        @self.socketio.on('connect')
        def handle_connect():
            client_id = self._get_client_id()
            logger.info(f"✅ 客户端连接: {client_id}")
            
            # 初始化客户端数据
            self.client_rooms[client_id] = set()
            
            # 发送连接确认
            emit('connected', {
                'client_id': client_id,
                'timestamp': time.time(),
                'message': 'Socket.IO网关连接成功'
            })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            client_id = self._get_client_id()
            logger.info(f"❌ 客户端断开: {client_id}")
            
            # 清理客户端数据
            if client_id in self.client_rooms:
                for task_id in self.client_rooms[client_id]:
                    if task_id in self.room_clients:
                        self.room_clients[task_id].discard(client_id)
                        if not self.room_clients[task_id]:
                            del self.room_clients[task_id]
                
                del self.client_rooms[client_id]
            
            if client_id in self.last_event_ids:
                del self.last_event_ids[client_id]
        
        @self.socketio.on('join_task')
        def handle_join_task(data):
            client_id = self._get_client_id()
            task_id = data.get('task_id')
            
            if not task_id:
                emit('error', {'message': '缺少task_id参数'})
                return
            
            # 加入任务房间
            join_room(f"task_{task_id}")
            
            # 更新客户端房间映射
            if client_id not in self.client_rooms:
                self.client_rooms[client_id] = set()
            self.client_rooms[client_id].add(task_id)
            
            if task_id not in self.room_clients:
                self.room_clients[task_id] = set()
            self.room_clients[task_id].add(client_id)
            
            logger.info(f"✅ 客户端 {client_id} 加入任务房间: {task_id}")
            
            # 发送任务快照和最近事件
            self._send_task_snapshot(task_id, client_id)
            
            emit('joined_task', {
                'task_id': task_id,
                'timestamp': time.time(),
                'message': f'已加入任务 {task_id} 的实时更新'
            })
        
        @self.socketio.on('leave_task')
        def handle_leave_task(data):
            client_id = self._get_client_id()
            task_id = data.get('task_id')
            
            if not task_id:
                emit('error', {'message': '缺少task_id参数'})
                return
            
            # 离开任务房间
            leave_room(f"task_{task_id}")
            
            # 更新客户端房间映射
            if client_id in self.client_rooms:
                self.client_rooms[client_id].discard(task_id)
            
            if task_id in self.room_clients:
                self.room_clients[task_id].discard(client_id)
                if not self.room_clients[task_id]:
                    del self.room_clients[task_id]
            
            logger.info(f"✅ 客户端 {client_id} 离开任务房间: {task_id}")
            
            emit('left_task', {
                'task_id': task_id,
                'timestamp': time.time(),
                'message': f'已离开任务 {task_id} 的实时更新'
            })
        
        @self.socketio.on('gift_card_input')
        def handle_gift_card_input(data):
            """处理礼品卡输入"""
            task_id = data.get('task_id')
            gift_card_data = data.get('gift_card_data', {})
            
            if not task_id:
                emit('error', {'message': '缺少task_id参数'})
                return
            
            # 提交用户输入到Redis
            from .message_service_sota import get_sota_message_service
            message_service = get_sota_message_service()
            
            success = message_service.submit_input(task_id, {
                'type': 'gift_card_input',
                'data': gift_card_data,
                'timestamp': time.time()
            })
            
            if success:
                emit('input_submitted', {
                    'task_id': task_id,
                    'type': 'gift_card_input',
                    'message': '礼品卡信息已提交'
                })
                logger.info(f"✅ 礼品卡输入已提交: {task_id}")
            else:
                emit('error', {'message': '提交礼品卡信息失败'})
    
    def _get_client_id(self):
        """获取客户端ID"""
        from flask import request
        return request.sid
    
    def _send_task_snapshot(self, task_id: str, client_id: str):
        """发送任务快照和最近事件"""
        try:
            from .message_service_sota import get_sota_message_service
            message_service = get_sota_message_service()
            
            # 获取任务快照
            snapshot = message_service.get_task_snapshot(task_id)
            if snapshot:
                self.socketio.emit('task_snapshot', snapshot, room=client_id)
            
            # 获取最近事件
            events = message_service.get_task_events(task_id, count=20)
            for event in reversed(events):  # 按时间顺序发送
                self.socketio.emit(event.get('event_type', 'unknown'), event, room=client_id)
                
        except Exception as e:
            logger.error(f"❌ 发送任务快照失败: {e}")
    
    def start(self):
        """启动网关服务"""
        if self.running:
            return
        
        self.running = True
        self.forwarder_thread = threading.Thread(target=self._stream_forwarder, daemon=True)
        self.forwarder_thread.start()
        
        logger.info("🚀 Socket.IO网关已启动")
    
    def stop(self):
        """停止网关服务"""
        self.running = False
        if self.forwarder_thread:
            self.forwarder_thread.join(timeout=5)
        
        logger.info("🛑 Socket.IO网关已停止")
    
    def _stream_forwarder(self):
        """Redis Stream转发器"""
        logger.info("🔄 Stream转发器开始工作...")
        
        while self.running:
            try:
                if not self.redis_client:
                    time.sleep(5)
                    continue
                
                # 从消费组读取事件
                messages = self.redis_client.xreadgroup(
                    self.CONSUMER_GROUP,
                    self.CONSUMER_NAME,
                    {self.BROADCAST_STREAM: '>'},
                    count=10,
                    block=1000  # 1秒超时
                )
                
                for stream, events in messages:
                    for event_id, fields in events:
                        self._forward_event(event_id, dict(fields))
                        
                        # 确认消息处理完成
                        self.redis_client.xack(self.BROADCAST_STREAM, self.CONSUMER_GROUP, event_id)
                
            except Exception as e:
                if self.running:
                    logger.error(f"❌ Stream转发失败: {e}")
                time.sleep(1)
    
    def _forward_event(self, event_id: str, event_data: Dict[str, Any]):
        """转发事件到对应的任务房间"""
        try:
            task_id = event_data.get('task_id')
            event_type = event_data.get('event_type')
            
            if not task_id or not event_type:
                return
            
            # 转发到任务房间
            room = f"task_{task_id}"
            self.socketio.emit(event_type, event_data, room=room)
            
            logger.debug(f"📤 事件已转发: {event_type} -> {room}")
            
        except Exception as e:
            logger.error(f"❌ 转发事件失败: {e}")

# 全局网关实例
_socketio_gateway = None

def init_socketio_gateway(socketio: SocketIO, redis_url: str = "redis://localhost:6379/0") -> SocketIOGateway:
    """初始化Socket.IO网关"""
    global _socketio_gateway
    _socketio_gateway = SocketIOGateway(socketio, redis_url)
    return _socketio_gateway

def get_socketio_gateway() -> SocketIOGateway:
    """获取Socket.IO网关实例"""
    global _socketio_gateway
    return _socketio_gateway
