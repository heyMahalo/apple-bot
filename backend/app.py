from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import logging
import os
import asyncio

from config.config import config
from task_manager import TaskManager
from websocket_handler import WebSocketHandler
from services.ip_service import IPService
from services.automation_service import AutomationService
from models.database import DatabaseManager, GiftCardStatus
from models.task import TaskStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # 启用CORS支持跨域请求
    CORS(app, origins="*")
    
    # 初始化SocketIO - 使用threading模式以兼容Playwright
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        logger=True,
        engineio_logger=True
    )
    
    # 🚀 优化启动速度：先初始化基础服务
    logger.info("🚀 正在初始化服务...")

    # 初始化IP服务（只初始化一次）
    ip_service = IPService(
        proxy_api_url=app.config.get('PROXY_API_URL', ''),
        rotation_enabled=app.config.get('PROXY_ROTATION_ENABLED', False)
    )

    # 初始化数据库管理器
    db_manager = DatabaseManager()

    # 🚀 初始化任务管理器（支持Celery）
    use_celery = app.config.get('USE_CELERY', True)
    task_manager = TaskManager(
        max_workers=app.config['MAX_CONCURRENT_TASKS'],
        use_celery=use_celery
    )

    # 初始化自动化服务（传入IP服务避免重复初始化）
    automation_service = AutomationService(ip_service=ip_service)

    # 设置TaskManager的自动化服务
    task_manager.set_automation_service(automation_service)

    # 初始化WebSocket处理器
    websocket_handler = WebSocketHandler(socketio, task_manager)

    # 🚀 异步初始化耗时服务，避免阻塞启动
    def init_services_async():
        try:
            # 初始化IP代理池
            ip_service.initialize_proxy_pool()
            logger.info("✅ IP代理池初始化完成")

            # 初始化消息服务（如果还没有初始化）
            from services.message_service import get_message_service
            from services.message_service_sota import get_sota_message_service

            message_service = get_message_service()
            sota_service = get_sota_message_service()
            logger.info("✅ 消息服务初始化完成")

        except Exception as e:
            logger.error(f"❌ 异步服务初始化失败: {e}")

    import threading
    services_init_thread = threading.Thread(target=init_services_async, daemon=True)
    services_init_thread.start()

    # 🚀 启动Celery事件监听器
    if use_celery:
        def start_celery_event_listener():
            """启动Celery事件监听器"""
            import redis
            import json
            import threading

            def listen_celery_events():
                try:
                    redis_client = redis.Redis.from_url('redis://localhost:6379/0')
                    pubsub = redis_client.pubsub()
                    pubsub.subscribe('celery_events')

                    logger.info("🚀 Celery事件监听器已启动")

                    for message in pubsub.listen():
                        if message['type'] == 'message':
                            try:
                                event_data = json.loads(message['data'])
                                event_name = event_data['event']
                                data = event_data['data']

                                # 转发到WebSocket
                                websocket_handler.broadcast(event_name, data)
                                logger.debug(f"📡 转发Celery事件: {event_name}")

                            except Exception as e:
                                logger.error(f"❌ 处理Celery事件失败: {e}")

                except Exception as e:
                    logger.error(f"❌ Celery事件监听器失败: {e}")

            # 在后台线程中运行
            listener_thread = threading.Thread(target=listen_celery_events, daemon=True)
            listener_thread.start()

        start_celery_event_listener()

    logger.info("✅ 核心服务初始化完成，后台服务正在异步加载")
    
    # REST API 路由
    @app.route('/', methods=['GET'])
    def index():
        """主页重定向到前端界面"""
        return send_from_directory('../frontend', 'inedx.html')
    
    @app.route('/simple.html', methods=['GET']) 
    def frontend():
        """前端界面"""
        return send_from_directory('../frontend', 'index.html')
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        return jsonify({
            'status': 'healthy',
            'version': '1.0.0',
            'timestamp': '2024-01-01T00:00:00Z'
        })
    
    @app.route('/api/tasks', methods=['GET'])
    def get_tasks():
        """获取所有任务"""
        tasks = [task.to_dict() for task in task_manager.get_all_tasks()]
        return jsonify({'tasks': tasks})

    @app.route('/api/tasks/active', methods=['GET'])
    def get_active_tasks():
        """获取活跃任务 - 用于智能轮询"""
        try:
            # 获取活跃任务
            active_tasks = task_manager.get_active_tasks()

            # 记录活跃任务检查
            all_tasks = task_manager.get_all_tasks()
            logger.info(f"📋 检查活跃任务: 总任务数={len(all_tasks)}")
            for task in active_tasks:
                logger.info(f"📋 任务 {task.id[:8]}: 状态={task.status}, Celery任务={task.id in task_manager.celery_tasks}")

            logger.info(f"📋 返回 {len(active_tasks)} 个活跃任务")

            # 返回任务字典列表和额外信息
            result = [task.to_dict() for task in active_tasks]
            return jsonify(result)

        except Exception as e:
            logger.error(f"获取活跃任务失败: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tasks/<task_id>', methods=['GET'])
    def get_task(task_id):
        """获取单个任务详情"""
        task = task_manager.get_task(task_id)
        if task:
            return jsonify(task.to_dict())
        return jsonify({'error': 'Task not found'}), 404
    
    @app.route('/api/tasks', methods=['POST'])
    def create_task():
        """创建新任务"""
        try:
            data = request.get_json()
            
            from models.task import TaskConfig, ProductConfig, AccountConfig, GiftCard

            # 解析产品配置
            product_config_data = data.get('product_config', {})
            product_config = ProductConfig(
                model=product_config_data.get('model', ''),
                finish=product_config_data.get('finish', ''),
                storage=product_config_data.get('storage', ''),
                trade_in=product_config_data.get('trade_in', 'No trade-in'),
                payment=product_config_data.get('payment', 'Buy'),
                apple_care=product_config_data.get('apple_care', 'No AppleCare+ Coverage')
            )

            # 解析账号配置
            account_config_data = data.get('account_config', {})
            logger.info(f"🔍 调试 - 接收到的account_config_data: {account_config_data}")

            # 获取Apple ID信息
            apple_email = account_config_data.get('email', '')
            apple_password = account_config_data.get('password', '')
            logger.info(f"🔍 调试 - 从前端获取: email='{apple_email}', password='{apple_password}'")

            # 从数据库获取对应账号的完整信息（包括电话号码）
            phone_number = account_config_data.get('phone_number', '07700900000')  # 默认英国手机号码
            if apple_email:
                # 查找数据库中的账号信息
                accounts = db_manager.get_all_accounts()
                for account in accounts:
                    if account.email == apple_email:
                        phone_number = account.phone_number or '07700900000'
                        # 如果前端没有提供密码，才使用数据库中的密码
                        if not apple_password and account.password:
                            apple_password = account.password
                        break

            # 创建账号配置对象（使用最终确定的信息）
            logger.info(f"🔍 调试 - 最终账号信息: email='{apple_email}', password='{apple_password}', phone_number='{phone_number}'")
            account_config = AccountConfig(
                email=apple_email,
                password=apple_password,
                phone_number=phone_number
            )
            logger.info(f"🔍 调试 - 创建的account_config: {account_config}")

            # 获取礼品卡信息（支持多张礼品卡）
            gift_cards = []
            
            # 新格式：多张礼品卡
            gift_cards_data = data.get('gift_cards', [])
            if gift_cards_data:
                for card_data in gift_cards_data:
                    if isinstance(card_data, dict):
                        gift_card = GiftCard(
                            number=card_data.get('gift_card_number', card_data.get('number', '')),
                            expected_status=card_data.get('status', 'has_balance')
                        )
                        gift_cards.append(gift_card)
                    elif isinstance(card_data, str):
                        # 兼容旧格式字符串
                        gift_card = GiftCard(number=card_data)
                        gift_cards.append(gift_card)
                logger.info(f"🎁 使用多张礼品卡: {len(gift_cards)} 张")
            
            # 兼容单张礼品卡格式
            elif data.get('gift_card_config'):
                gift_card_config = data.get('gift_card_config')
                if gift_card_config.get('gift_card_number'):
                    gift_card = GiftCard(
                        number=gift_card_config.get('gift_card_number'),
                        expected_status=gift_card_config.get('status', 'has_balance')
                    )
                    gift_cards.append(gift_card)
                    logger.info(f"🎁 使用单张礼品卡: {gift_card.number[:4]}****")
            
            # 如果没有礼品卡，记录警告
            if not gift_cards:
                logger.warning("⚠️ 未配置任何礼品卡")
            
            # 向后兼容字段
            gift_card_code = gift_cards[0].number if gift_cards else None

            # 创建任务配置
            task_config = TaskConfig(
                name=data.get('name', ''),
                url=data.get('url', ''),
                product_config=product_config,
                account_config=account_config,
                enabled=data.get('enabled', True),
                priority=data.get('priority', 1),
                gift_cards=gift_cards,
                use_proxy=data.get('use_proxy', False),
                apple_email=apple_email,
                apple_password=apple_password,
                phone_number=phone_number,
                gift_card_code=gift_card_code
            )
            
            # 创建任务
            task = task_manager.create_task(task_config)
            
            # 通知WebSocket客户端
            websocket_handler.broadcast('task_created', task.to_dict())
            
            return jsonify({
                'success': True,
                'task_id': task.id,
                'task': task.to_dict()
            }), 201
            
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}")
            return jsonify({'error': str(e)}), 400
    
    @app.route('/api/tasks/<task_id>/start', methods=['POST'])
    def start_task(task_id):
        """启动任务"""
        success = task_manager.start_task(task_id, websocket_handler)
        if success:
            # 🚀 立即发送启动成功事件，确保前端快速响应
            if websocket_handler:
                websocket_handler.broadcast('task_start_success', {'task_id': task_id})
            return jsonify({'success': True, 'message': 'Task started'})
        else:
            # 发送启动失败事件
            if websocket_handler:
                websocket_handler.broadcast('task_start_error', {
                    'task_id': task_id,
                    'message': 'Failed to start task'
                })
            return jsonify({'error': 'Failed to start task'}), 400
    
    @app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
    def cancel_task(task_id):
        """取消任务"""
        success = task_manager.cancel_task(task_id)
        if success:
            # 🚀 立即发送取消成功事件
            if websocket_handler:
                websocket_handler.broadcast('task_cancel_success', {'task_id': task_id})

            task = task_manager.get_task(task_id)
            if task:
                websocket_handler.broadcast('task_update', task.to_dict())
            return jsonify({'success': True, 'message': 'Task cancelled'})
        else:
            # 发送取消失败事件
            if websocket_handler:
                websocket_handler.broadcast('task_cancel_error', {
                    'task_id': task_id,
                    'message': 'Failed to cancel task'
                })
            return jsonify({'error': 'Failed to cancel task'}), 400

    @app.route('/api/tasks/<task_id>/gift-card', methods=['POST'])
    def submit_gift_card(task_id):
        """提交任务的礼品卡信息"""
        try:
            data = request.get_json()
            code = data.get('code', '').strip().upper()  # 转换为大写
            note = data.get('note', '').strip()

            if not code:
                return jsonify({'error': '礼品卡号码不能为空'}), 400

            # 验证礼品卡号码格式（16位字母数字组合）
            import re
            if not re.match(r'^[A-Z0-9]{16}$', code):
                return jsonify({'error': '礼品卡号码格式错误，应为16位字母数字组合'}), 400

            logger.info(f"🎁 收到任务 {task_id} 的礼品卡信息: {code[:4]}****")

            # 获取任务
            task = task_manager.get_task(task_id)
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            if task.status != TaskStatus.WAITING_GIFT_CARD_INPUT:
                return jsonify({'error': f'任务状态错误，当前状态: {task.status.value}'}), 400

            # 更新任务的礼品卡信息
            from models.task import GiftCard
            gift_card = GiftCard(number=code)

            # 如果任务配置中没有礼品卡，添加一个
            if not task.config.gift_cards:
                task.config.gift_cards = []

            # 添加新的礼品卡或更新现有的
            task.config.gift_cards.append(gift_card)
            task.config.gift_card_code = code  # 向后兼容

            # 添加日志
            task.add_log(f"🎁 收到礼品卡信息: {code[:4]}****", "info")

            # 更新任务状态为继续执行
            task.status = TaskStatus.STAGE_4_GIFT_CARD
            task.current_step = "stage_4_gift_card"
            task.add_log("🔄 礼品卡信息已提交，任务继续执行", "success")

            # 保存任务到数据库
            task_manager._persist_task(task)

            # 发送WebSocket更新
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())
                websocket_handler.broadcast('task_status_update', {
                    'task_id': task_id,
                    'status': task.status.value,
                    'progress': task.progress,
                    'message': '礼品卡信息已提交，任务继续执行'
                })

            # 简化逻辑：只更新任务状态，让等待循环自然退出
            logger.info(f"🔄 礼品卡信息已保存，更新任务状态让等待循环退出")
            # 将任务状态从 WAITING_GIFT_CARD_INPUT 改为 STAGE_4_GIFT_CARD
            # 这样 _handle_gift_card_input 中的等待循环会检测到状态变化并退出
            task.status = TaskStatus.STAGE_4_GIFT_CARD
            logger.info(f"✅ 任务状态已更新为 {task.status}，等待循环将自动退出")

            return jsonify({
                'success': True,
                'message': '礼品卡信息已提交，任务继续执行',
                'task_status': task.status.value
            })

        except Exception as e:
            logger.error(f"❌ 提交礼品卡信息失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tasks/<task_id>/trigger-gift-card-input', methods=['POST'])
    def trigger_gift_card_input(task_id):
        """手动触发礼品卡输入事件（用于测试）"""
        try:
            task = task_manager.get_task(task_id)
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            if task.status != TaskStatus.WAITING_GIFT_CARD_INPUT:
                return jsonify({'error': f'任务状态错误，当前状态: {task.status.value}'}), 400

            # 发送礼品卡输入请求事件
            if websocket_handler:
                websocket_handler.send_task_event("gift_card_input_required", task_id, {
                    "message": "请在下方输入礼品卡信息，点击确认后系统将自动继续执行",
                    "status": "waiting_gift_card_input",
                    "task_name": task.config.name,
                    "current_step": "礼品卡输入"
                })

            return jsonify({
                'success': True,
                'message': '礼品卡输入事件已触发'
            })

        except Exception as e:
            logger.error(f"❌ 触发礼品卡输入事件失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tasks/<task_id>/set-status/<status>', methods=['POST'])
    def set_task_status(task_id, status):
        """设置任务状态（用于测试）"""
        try:
            task = task_manager.get_task(task_id)
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            # 设置任务状态
            if status == 'waiting_gift_card_input':
                task.status = TaskStatus.WAITING_GIFT_CARD_INPUT
            elif status == 'running':
                task.status = TaskStatus.RUNNING
            elif status == 'completed':
                task.status = TaskStatus.COMPLETED
            elif status == 'failed':
                task.status = TaskStatus.FAILED
            else:
                return jsonify({'error': f'不支持的状态: {status}'}), 400

            # 保存任务
            task_manager._persist_task(task)

            # 发送WebSocket更新
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())
                websocket_handler.broadcast('task_status_update', {
                    'task_id': task_id,
                    'status': task.status.value,
                    'progress': task.progress,
                    'message': f'任务状态已设置为: {status}'
                })

            return jsonify({
                'success': True,
                'message': f'任务状态已设置为: {status}',
                'task_status': task.status.value
            })

        except Exception as e:
            logger.error(f"❌ 设置任务状态失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/system/status', methods=['GET'])
    def get_system_status():
        """获取系统状态"""
        active_tasks = task_manager.get_active_tasks()
        ip_info = ip_service.get_current_ip_info()
        
        status = {
            'total_tasks': len(task_manager.tasks),
            'active_tasks': len(active_tasks),
            'max_concurrent': task_manager.max_workers,
            'ip_info': ip_info,
            'proxy_rotation_enabled': ip_service.rotation_enabled
        }
        return jsonify(status)
    
    @app.route('/api/system/rotate-ip', methods=['POST'])
    def rotate_ip():
        """手动轮换IP"""
        if not ip_service.rotation_enabled:
            return jsonify({'error': 'Proxy rotation is disabled'}), 400
        
        # 创建异步任务来执行IP轮换    
        async def do_rotation():
            return await ip_service.rotate_proxy(force=True)
        
        new_proxy = asyncio.get_event_loop().run_until_complete(do_rotation())
        if new_proxy:
            return jsonify({
                'success': True,
                'new_proxy': new_proxy.to_dict(),
                'message': 'IP rotated successfully'
            })
        return jsonify({'error': 'Failed to rotate IP'}), 500
    
    # 🔄 新增：完善的IP管理接口
    @app.route('/api/ip/status', methods=['GET'])
    def get_ip_status():
        """获取当前IP状态和代理池信息"""
        try:
            current_ip = ip_service.get_current_ip_info()
            pool_status = ip_service.get_proxy_pool_status()
            
            return jsonify({
                'current_ip': current_ip,
                'proxy_pool': pool_status,
                'rotation_enabled': ip_service.rotation_enabled,
                'gift_card_rotation_enabled': ip_service.gift_card_rotation_enabled
            })
        except Exception as e:
            logger.error(f"Failed to get IP status: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ip/rotate-for-gift-card', methods=['POST'])
    def rotate_ip_for_gift_card():
        """为特定礼品卡轮换IP"""
        try:
            data = request.get_json()
            task_id = data.get('task_id', 'manual')
            gift_card_number = data.get('gift_card_number', '')
            
            if not gift_card_number:
                return jsonify({'error': 'Gift card number is required'}), 400
            
            new_proxy = asyncio.create_task(
                ip_service.rotate_ip_for_gift_card(task_id, gift_card_number)
            )
            new_proxy = asyncio.get_event_loop().run_until_complete(new_proxy)
            
            if new_proxy:
                return jsonify({
                    'success': True,
                    'new_proxy': new_proxy.to_dict(),
                    'message': f'IP rotated for gift card {gift_card_number[:4]}****'
                })
            return jsonify({'error': 'Failed to rotate IP for gift card'}), 500
            
        except Exception as e:
            logger.error(f"Failed to rotate IP for gift card: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ip/block', methods=['POST'])
    def block_ip():
        """手动标记IP为被封禁"""
        try:
            data = request.get_json()
            ip_address = data.get('ip_address', '')
            reason = data.get('reason', 'Manual block')
            
            if not ip_address:
                return jsonify({'error': 'IP address is required'}), 400
            
            ip_service.mark_ip_blocked(ip_address, reason)
            return jsonify({
                'success': True,
                'message': f'IP {ip_address} marked as blocked',
                'reason': reason
            })
            
        except Exception as e:
            logger.error(f"Failed to block IP: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ip/gift-card-history/<gift_card_number>', methods=['GET'])  
    def get_gift_card_ip_history(gift_card_number):
        """获取礼品卡的IP使用历史"""
        try:
            history = ip_service.get_gift_card_ip_history(gift_card_number)
            return jsonify({
                'gift_card': gift_card_number[:4] + '****',
                'ip_history': history,
                'usage_count': len(history)
            })
        except Exception as e:
            logger.error(f"Failed to get gift card IP history: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/ip/settings', methods=['GET', 'PUT'])
    def ip_settings():
        """获取或更新IP轮换设置"""
        if request.method == 'GET':
            return jsonify({
                'rotation_enabled': ip_service.rotation_enabled,
                'gift_card_rotation_enabled': ip_service.gift_card_rotation_enabled,
                'max_gift_card_per_ip': ip_service.max_gift_card_per_ip,
                'rotation_interval': ip_service.rotation_interval
            })
        
        elif request.method == 'PUT':
            try:
                data = request.get_json()
                
                if 'rotation_enabled' in data:
                    ip_service.rotation_enabled = data['rotation_enabled']
                if 'gift_card_rotation_enabled' in data:
                    ip_service.gift_card_rotation_enabled = data['gift_card_rotation_enabled']
                if 'max_gift_card_per_ip' in data:
                    ip_service.max_gift_card_per_ip = data['max_gift_card_per_ip']
                if 'rotation_interval' in data:
                    ip_service.rotation_interval = data['rotation_interval']
                
                return jsonify({
                    'success': True,
                    'message': 'IP settings updated successfully'
                })
                
            except Exception as e:
                logger.error(f"Failed to update IP settings: {str(e)}")
                return jsonify({'error': str(e)}), 500
    
    @app.route('/api/config/iphone-configs', methods=['GET'])
    def get_iphone_configs():
        """获取iPhone配置信息"""
        try:
            import os
            import json

            # 获取iPhone配置文件路径
            config_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'iphone_configs.json')

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
                return jsonify(configs)
            else:
                return jsonify({'error': 'iPhone configs not found'}), 404

        except Exception as e:
            logger.error(f"Failed to load iPhone configs: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/config/parse-url', methods=['POST'])
    def parse_iphone_url():
        """解析iPhone URL并返回配置信息"""
        try:
            data = request.get_json()
            url = data.get('url', '')

            # URL解析逻辑
            import re
            pattern = r'https://www\.apple\.com/uk/shop/buy-iphone/([^/]+)/([^/]+)-([^/]+)-([^/]+)'
            match = re.match(pattern, url)

            if match:
                model, size, storage, color = match.groups()

                return jsonify({
                    'success': True,
                    'config': {
                        'model': model,
                        'size': size,
                        'storage': storage,
                        'color': color
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Invalid iPhone URL format'
                }), 400

        except Exception as e:
            logger.error(f"Failed to parse URL: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/config/generate-url', methods=['POST'])
    def generate_iphone_url():
        """根据配置生成iPhone URL"""
        try:
            data = request.get_json()
            model = data.get('model')
            size = data.get('size')
            storage = data.get('storage')
            color = data.get('color')

            if not all([model, size, storage, color]):
                return jsonify({'error': 'Missing required parameters'}), 400

            url = f"https://www.apple.com/uk/shop/buy-iphone/{model}/{size}-{storage}-{color}"

            return jsonify({
                'success': True,
                'url': url
            })

        except Exception as e:
            logger.error(f"Failed to generate URL: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/config/product-options', methods=['GET'])
    def get_product_options():
        """获取产品配置选项"""
        try:
            # 读取清理后的iPhone产品数据
            import os
            import json
            
            # 获取根目录路径 (从backend目录向上一级到apple_bot_system)
            root_dir = os.path.dirname(os.path.dirname(__file__))
            iphone_data_path = os.path.join(root_dir, 'iphone_products_clean.json')
            
            if os.path.exists(iphone_data_path):
                with open(iphone_data_path, 'r', encoding='utf-8') as f:
                    iphone_data = json.load(f)
                
                # 提取所有可用的配置选项
                all_models = []
                all_finishes = []
                all_storages = []
                all_urls = {}
                
                for product_name, product_info in iphone_data.items():
                    # 收集URL映射
                    all_urls[product_name] = product_info['url']
                    
                    configs = product_info.get('configurations', {})
                    
                    # 收集型号选项
                    if 'Model' in configs:
                        for model in configs['Model']:
                            if model not in all_models:
                                all_models.append(model)
                    
                    # 收集颜色选项
                    if 'Finish' in configs:
                        for finish in configs['Finish']:
                            if finish not in all_finishes:
                                all_finishes.append(finish)
                    
                    # 收集存储选项
                    if 'Storage' in configs:
                        for storage in configs['Storage']:
                            if storage not in all_storages:
                                all_storages.append(storage)
                
                # 构建选项数据
                options = {
                    'products': list(iphone_data.keys()),  # 产品列表
                    'product_urls': all_urls,  # 产品URL映射
                    'models': sorted(all_models) if all_models else [
                        'iPhone 16 Pro 6.3-inch display',
                        'iPhone 16 Pro Max 6.9-inch display',
                        'iPhone 16 6.1-inch display',
                        'iPhone 16 Plus 6.7-inch display'
                    ],
                    'finishes': sorted(all_finishes) if all_finishes else [
                        'Desert Titanium',
                        'Natural Titanium', 
                        'White Titanium',
                        'Black Titanium',
                        'Ultramarine',
                        'Teal',
                        'Pink',
                        'White',
                        'Black'
                    ],
                    'storages': sorted(all_storages, key=lambda x: int(x.replace('GB', '').replace('TB', '000'))) if all_storages else [
                        '128GB',
                        '256GB', 
                        '512GB',
                        '1TB'
                    ],
                    'trade_in_options': [
                        'No trade-in',
                        'iPhone 15 Pro',
                        'iPhone 15',
                        'iPhone 14 Pro',
                        'iPhone 14',
                        'iPhone 13 Pro',
                        'iPhone 13'
                    ]
                }

                product_configs = {
                    'iphone': {
                        'options': options
                    }
                }

                return jsonify(product_configs)
            else:
                # 如果文件不存在，返回默认配置
                return jsonify({
                    'iphone': {
                        'options': {
                            'models': ['iPhone 16 Pro', 'iPhone 16'],
                            'finishes': ['Natural Titanium', 'Black Titanium'],
                            'storages': ['128GB', '256GB', '512GB', '1TB'],
                            'trade_in_options': ['No trade-in']
                        }
                    }
                })

        except Exception as e:
            logger.error(f"获取产品配置选项失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tasks/<task_id>/debug-browser', methods=['GET'])
    def debug_browser_status(task_id):
        """调试浏览器状态"""
        try:
            task = task_manager.get_task(task_id)
            if not task:
                return jsonify({'error': '任务不存在'}), 404

            debug_info = {
                'task_id': task_id,
                'task_status': task.status.value,
                'automation_service_available': task_manager.automation_service is not None,
                'browser_page_exists': False,
                'page_url': None,
                'page_title': None
            }

            if task_manager.automation_service:
                # 检查浏览器页面是否存在
                page = task_manager.automation_service.pages.get(task_id)
                if page:
                    debug_info['browser_page_exists'] = True
                    try:
                        debug_info['page_url'] = page.url
                        debug_info['page_title'] = page.title()
                    except Exception as e:
                        debug_info['page_error'] = str(e)

            return jsonify(debug_info)

        except Exception as e:
            logger.error(f"调试浏览器状态失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # 🎁 礼品卡管理API
    @app.route('/api/gift-cards', methods=['GET'])
    def get_gift_cards():
        """获取所有礼品卡"""
        try:
            db_manager = DatabaseManager()
            gift_cards = db_manager.get_all_gift_cards()
            return jsonify(gift_cards)
        except Exception as e:
            logger.error(f"获取礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards', methods=['POST'])
    def add_gift_card():
        """添加新礼品卡"""
        try:
            data = request.get_json()
            gift_card_number = data.get('gift_card_number', '').strip().upper()
            status = data.get('status', '有额度')
            notes = data.get('notes', '')

            if not gift_card_number:
                return jsonify({'error': '礼品卡号码不能为空'}), 400

            # 验证礼品卡号码格式
            import re
            if not re.match(r'^[A-Z0-9]{16}$', gift_card_number):
                return jsonify({'error': '礼品卡号码格式错误，应为16位字母数字组合'}), 400

            db_manager = DatabaseManager()
            gift_card_id = db_manager.add_gift_card(gift_card_number, status, notes)

            return jsonify({
                'success': True,
                'message': '礼品卡添加成功',
                'gift_card_id': gift_card_id
            })
        except Exception as e:
            logger.error(f"添加礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards/<int:gift_card_id>', methods=['PUT'])
    def update_gift_card(gift_card_id):
        """更新礼品卡"""
        try:
            data = request.get_json()
            status = data.get('status')
            notes = data.get('notes')

            db_manager = DatabaseManager()
            success = db_manager.update_gift_card(gift_card_id, status, notes)

            if success:
                return jsonify({'success': True, 'message': '礼品卡更新成功'})
            else:
                return jsonify({'error': '礼品卡不存在'}), 404
        except Exception as e:
            logger.error(f"更新礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards/<int:gift_card_id>', methods=['DELETE'])
    def delete_gift_card(gift_card_id):
        """删除礼品卡"""
        try:
            db_manager = DatabaseManager()
            success = db_manager.delete_gift_card(gift_card_id)

            if success:
                return jsonify({'success': True, 'message': '礼品卡删除成功'})
            else:
                return jsonify({'error': '礼品卡不存在'}), 404
        except Exception as e:
            logger.error(f"删除礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # 👤 账号管理API
    @app.route('/api/accounts', methods=['GET'])
    def get_accounts():
        """获取所有账号"""
        try:
            db_manager = DatabaseManager()
            accounts = db_manager.get_all_accounts()
            return jsonify(accounts)
        except Exception as e:
            logger.error(f"获取账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts', methods=['POST'])
    def add_account():
        """添加新账号"""
        try:
            data = request.get_json()
            email = data.get('email', '').strip()
            password = data.get('password', '').strip()
            phone_number = data.get('phone_number', '').strip()
            status = data.get('status', '可用')
            notes = data.get('notes', '')

            if not email or not password:
                return jsonify({'error': '邮箱和密码不能为空'}), 400

            db_manager = DatabaseManager()
            account_id = db_manager.add_account(email, password, phone_number, status, notes)

            return jsonify({
                'success': True,
                'message': '账号添加成功',
                'account_id': account_id
            })
        except Exception as e:
            logger.error(f"添加账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts/<int:account_id>', methods=['PUT'])
    def update_account(account_id):
        """更新账号"""
        try:
            data = request.get_json()
            password = data.get('password')
            phone_number = data.get('phone_number')
            status = data.get('status')
            notes = data.get('notes')

            db_manager = DatabaseManager()
            success = db_manager.update_account(account_id, password, phone_number, status, notes)

            if success:
                return jsonify({'success': True, 'message': '账号更新成功'})
            else:
                return jsonify({'error': '账号不存在'}), 404
        except Exception as e:
            logger.error(f"更新账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
    def delete_account(account_id):
        """删除账号"""
        try:
            db_manager = DatabaseManager()
            success = db_manager.delete_account(account_id)

            if success:
                return jsonify({'success': True, 'message': '账号删除成功'})
            else:
                return jsonify({'error': '账号不存在'}), 404
        except Exception as e:
            logger.error(f"删除账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)