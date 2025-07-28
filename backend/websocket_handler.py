from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, socketio: SocketIO, task_manager):
        self.socketio = socketio
        self.task_manager = task_manager
        self.connected_clients = set()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """设置WebSocket事件处理器"""
        
        @self.socketio.on('connect')
        def handle_connect(auth):
            """客户端连接"""
            client_id = request.sid
            logger.info(f"Client connected: {client_id}")
            self.connected_clients.add(client_id)

            # 发送当前所有任务状态
            tasks = [task.to_dict() for task in self.task_manager.get_all_tasks()]
            emit('initial_tasks', {'tasks': tasks})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """客户端断开"""
            client_id = request.sid
            logger.info(f"Client disconnected: {client_id}")
            self.connected_clients.discard(client_id)
        
        @self.socketio.on('get_tasks')
        def handle_get_tasks():
            """获取所有任务"""
            tasks = [task.to_dict() for task in self.task_manager.get_all_tasks()]
            emit('tasks_list', {'tasks': tasks})
        
        @self.socketio.on('create_task')
        def handle_create_task(data):
            """创建新任务"""
            logger.info("🔥 WebSocket create_task 事件被触发!")
            logger.info(f"🔥 接收到的原始数据类型: {type(data)}")
            logger.info(f"🔥 接收到的原始数据: {data}")

            # 立即发送确认消息，证明WebSocket通信正常
            self.socketio.emit('debug_message', {'message': 'WebSocket收到create_task事件', 'data_keys': list(data.keys()) if isinstance(data, dict) else 'not_dict'})

            try:
                from models.task import TaskConfig, ProductConfig, AccountConfig

                # 创建专门的礼品卡调试日志
                from datetime import datetime
                debug_log_path = f"websocket_gift_card_debug.log"
                with open(debug_log_path, 'a', encoding='utf-8') as debug_file:
                    debug_file.write(f"\n=== WebSocket 礼品卡调试 {datetime.now()} ===\n")
                    debug_file.write(f"1. 接收到的原始数据:\n")
                    debug_file.write(f"   gift_card_config: {data.get('gift_card_config')}\n")
                    debug_file.write(f"   gift_cards: {data.get('gift_cards')}\n")
                    debug_file.write(f"   所有数据键: {list(data.keys())}\n\n")

                # 解析产品配置
                product_config = ProductConfig(
                    model=data['product_config']['model'],
                    finish=data['product_config']['finish'],
                    storage=data['product_config']['storage'],
                    trade_in=data['product_config'].get('trade_in', 'No trade-in'),
                    payment=data['product_config'].get('payment', 'Buy'),
                    apple_care=data['product_config'].get('apple_care', 'No AppleCare+ Coverage')
                )

                # 解析账号配置
                account_config_data = data.get('account_config', {})
                account_config = AccountConfig(
                    email=account_config_data.get('email', ''),
                    password=account_config_data.get('password', ''),
                    phone_number=account_config_data.get('phone_number', '07700900000')
                )

                # 获取礼品卡信息（新格式：前端发送的多张礼品卡数组）
                gift_cards = []
                
                # 处理新格式：gift_cards数组
                frontend_gift_cards = data.get('gift_cards', [])
                if frontend_gift_cards and len(frontend_gift_cards) > 0:
                    for card_data in frontend_gift_cards:
                        if isinstance(card_data, dict):
                            # 新格式：{gift_card_number: "xxx", status: "xxx"}
                            gift_card_number = card_data.get('gift_card_number', '')
                            gift_card_status = card_data.get('status', 'has_balance')
                            
                            if gift_card_number:
                                from models.task import GiftCard
                                gift_card = GiftCard(
                                    number=gift_card_number,
                                    expected_status=gift_card_status
                                )
                                gift_cards.append(gift_card)
                                logger.info(f"🎁 WebSocket添加礼品卡: {gift_card_number[:4]}**** (状态: {gift_card_status})")
                        else:
                            # 兼容旧格式：字符串
                            logger.warning(f"⚠️ 发现旧格式礼品卡数据: {card_data}")
                
                # 设置向后兼容的gift_card_code
                gift_card_code = gift_cards[0].number if gift_cards else None
                
                logger.info(f"🎁 WebSocket最终处理结果: {len(gift_cards)}张礼品卡")
                for i, card in enumerate(gift_cards):
                    logger.info(f"   卡片{i+1}: {card.number[:4]}**** (状态: {card.expected_status})")

                # 写入礼品卡处理结果到调试日志
                with open(debug_log_path, 'a', encoding='utf-8') as debug_file:
                    debug_file.write(f"2. 礼品卡处理结果:\n")
                    debug_file.write(f"   gift_cards数量: {len(gift_cards)}\n")
                    debug_file.write(f"   gift_card_code: {gift_card_code}\n")
                    debug_file.write(f"   gift_cards详情: {[f'{card.number[:4]}****({card.expected_status})' for card in gift_cards]}\n\n")

                task_config = TaskConfig(
                    name=data['name'],
                    url=data['url'],
                    product_config=product_config,
                    account_config=account_config,
                    enabled=data.get('enabled', True),
                    priority=data.get('priority', 1),
                    gift_cards=gift_cards,
                    gift_card_code=gift_card_code,
                    use_proxy=data.get('use_proxy', False)
                )

                # 写入TaskConfig创建结果到调试日志
                with open(debug_log_path, 'a', encoding='utf-8') as debug_file:
                    debug_file.write(f"3. TaskConfig创建结果:\n")
                    debug_file.write(f"   task_config.gift_cards: {task_config.gift_cards}\n")
                    debug_file.write(f"   task_config.gift_card_code: {task_config.gift_card_code}\n")
                    debug_file.write(f"   TaskConfig完整内容: {vars(task_config)}\n")
                    debug_file.write(f"=== WebSocket 调试结束 ===\n\n")
                
                # 创建任务
                task = self.task_manager.create_task(task_config)

                # 记录创建的任务ID到调试日志
                with open(debug_log_path, 'a', encoding='utf-8') as debug_file:
                    debug_file.write(f"4. 创建的任务ID: {task.id}\n")
                    debug_file.write(f"   任务状态: {task.status}\n")
                    debug_file.write(f"   任务config是否相同: {task.config is task_config}\n")
                
                # 通知所有客户端
                self.broadcast('task_created', task.to_dict())
                
                emit('task_create_success', {
                    'task_id': task.id,
                    'message': 'Task created successfully'
                })
                
            except Exception as e:
                logger.error(f"Failed to create task: {str(e)}")
                emit('task_create_error', {'error': str(e)})
        
        @self.socketio.on('start_task')
        def handle_start_task(data):
            """启动任务"""
            task_id = data.get('task_id')
            if not task_id:
                emit('error', {'message': 'Task ID is required'})
                return
            
            success = self.task_manager.start_task(task_id, self)
            if success:
                emit('task_start_success', {'task_id': task_id})
            else:
                emit('task_start_error', {
                    'task_id': task_id,
                    'message': 'Failed to start task'
                })
        
        @self.socketio.on('cancel_task')
        def handle_cancel_task(data):
            """取消任务"""
            task_id = data.get('task_id')
            if not task_id:
                emit('error', {'message': 'Task ID is required'})
                return
            
            success = self.task_manager.cancel_task(task_id, self)
            if success:
                emit('task_cancel_success', {'task_id': task_id})
            else:
                emit('task_cancel_error', {
                    'task_id': task_id,
                    'message': 'Failed to cancel task'
                })
        
        @self.socketio.on('get_task_detail')
        def handle_get_task_detail(data):
            """获取任务详情"""
            task_id = data.get('task_id')
            if not task_id:
                emit('error', {'message': 'Task ID is required'})
                return
            
            task = self.task_manager.get_task(task_id)
            if task:
                emit('task_detail', task.to_dict())
            else:
                emit('error', {'message': 'Task not found'})
        
        @self.socketio.on('delete_task')
        def handle_delete_task(data):
            """删除任务"""
            task_id = data.get('task_id')
            if not task_id:
                emit('error', {'message': 'Task ID is required'})
                return
            
            # 使用任务管理器的删除方法
            success = self.task_manager.delete_task(task_id, self)
            if success:
                emit('task_delete_success', {'task_id': task_id})
            else:
                emit('task_delete_error', {'message': 'Task not found'})
        
        @self.socketio.on('get_system_status')
        def handle_get_system_status():
            """获取系统状态"""
            active_tasks = self.task_manager.get_active_tasks()
            status = {
                'total_tasks': len(self.task_manager.tasks),
                'active_tasks': len(active_tasks),
                'max_concurrent': self.task_manager.max_workers,
                'connected_clients': len(self.connected_clients)
            }
            emit('system_status', status)
        
        @self.socketio.on('rerun_task')
        def handle_rerun_task(data):
            """重新运行任务 - 重置原任务并重新启动"""
            task_id = data.get('task_id')
            if not task_id:
                emit('error', {'message': 'Task ID is required'})
                return
            
            # 重置并重新启动任务
            success = self.task_manager.reset_and_restart_task(task_id, self)
            if success:
                emit('rerun_task_success', {'task_id': task_id})
            else:
                emit('rerun_task_error', {
                    'task_id': task_id,
                    'message': 'Failed to rerun task'
                })
    
    def broadcast(self, event: str, data: dict):
        """向所有连接的客户端广播消息"""
        self.socketio.emit(event, data)

    def emit(self, event: str, data: dict, room=None):
        """发送消息到特定房间或广播"""
        if room:
            self.socketio.emit(event, data, room=room)
        else:
            self.socketio.emit(event, data)
    
    def send_step_update(self, task_id: str, step: str, status: str, progress: float, message: str = ""):
        """发送详细的步骤更新"""
        data = {
            'task_id': task_id,
            'step': step,
            'status': status,  # 'started', 'progress', 'completed', 'failed'
            'progress': progress,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.broadcast('step_update', data)
    
    def send_task_log(self, task_id: str, level: str, message: str):
        """发送任务日志"""
        data = {
            'task_id': task_id,
            'level': level,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.broadcast('task_log', data)