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
from models.database import DatabaseManager, GiftCardStatus

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
    
    # 初始化SocketIO
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        async_mode='eventlet',
        logger=True,
        engineio_logger=True
    )
    
    # 初始化服务
    task_manager = TaskManager(max_workers=app.config['MAX_CONCURRENT_TASKS'])
    ip_service = IPService(
        proxy_api_url=app.config.get('PROXY_API_URL', ''),
        rotation_enabled=app.config.get('PROXY_ROTATION_ENABLED', False)
    )

    # 初始化WebSocket处理器
    websocket_handler = WebSocketHandler(socketio, task_manager)

    # 初始化数据库管理器
    db_manager = DatabaseManager()
    
    # 初始化IP代理池
    ip_service.initialize_proxy_pool()
    
    # REST API 路由
    @app.route('/', methods=['GET'])
    def index():
        """主页重定向到前端界面"""
        return send_from_directory('../frontend', 'simple.html')
    
    @app.route('/simple.html', methods=['GET']) 
    def frontend():
        """前端界面"""
        return send_from_directory('../frontend', 'simple.html')
    
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
            return jsonify({'success': True, 'message': 'Task started'})
        return jsonify({'error': 'Failed to start task'}), 400
    
    @app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
    def cancel_task(task_id):
        """取消任务"""
        success = task_manager.cancel_task(task_id)
        if success:
            task = task_manager.get_task(task_id)
            if task:
                websocket_handler.broadcast('task_update', task.to_dict())
            return jsonify({'success': True, 'message': 'Task cancelled'})
        return jsonify({'error': 'Failed to cancel task'}), 400
    
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
                        'iPhone 13',
                        'iPhone 12 Pro',
                        'iPhone 12'
                    ],
                    'payment_options': [
                        'Buy',
                        'Monthly Installments'
                    ],
                    'apple_care_options': [
                        'No AppleCare+ Coverage',
                        'Monthly coverage until cancelled',
                        'Two years of coverage',
                        'AppleCare+ for iPhone',
                        'AppleCare+ with Theft and Loss'
                    ]
                }
                
                logger.info(f"Loaded product options from iPhone data: {len(options['products'])} products")
                return jsonify(options)
                
            else:
                logger.warning(f"iPhone data file not found at {iphone_data_path}, using fallback data")
                
        except Exception as e:
            logger.error(f"Failed to load iPhone data: {str(e)}")
        
        # 如果读取失败，返回默认数据
        fallback_options = {
            'products': [
                'iPhone 16 Pro & iPhone 16 Pro Max',
                'iPhone 16 & iPhone 16 Plus', 
                'iPhone 15 & iPhone 15 Plus'
            ],
            'product_urls': {
                'iPhone 16 Pro & iPhone 16 Pro Max': 'https://www.apple.com/uk/shop/buy-iphone/iphone-16-pro',
                'iPhone 16 & iPhone 16 Plus': 'https://www.apple.com/uk/shop/buy-iphone/iphone-16',
                'iPhone 15 & iPhone 15 Plus': 'https://www.apple.com/uk/shop/buy-iphone/iphone-15'
            },
            'models': [
                'iPhone 16 Pro',
                'iPhone 16 Pro Max',
                'iPhone 16',
                'iPhone 16 Plus'
            ],
            'finishes': [
                'Natural Titanium',
                'Blue Titanium',
                'White Titanium',
                'Black Titanium'
            ],
            'storages': [
                '128GB',
                '256GB',
                '512GB',
                '1TB'
            ],
            'trade_in_options': [
                'No trade-in',
                'iPhone 15 Pro',
                'iPhone 14 Pro',
                'iPhone 13 Pro'
            ],
            'payment_options': [
                'Buy',
                'Monthly Installments'
            ],
            'apple_care_options': [
                'No AppleCare+ Coverage',
                'AppleCare+ for iPhone',
                'AppleCare+ with Theft and Loss'
            ]
        }
        return jsonify(fallback_options)

    # ==================== 数据库管理API ====================

    # 账号管理API
    @app.route('/api/accounts', methods=['GET'])
    def get_accounts():
        """获取所有账号"""
        try:
            accounts = db_manager.get_all_accounts()
            return jsonify([{
                'id': acc.id,
                'email': acc.email,
                'password': acc.password,  # 包含密码用于任务创建
                'phone_number': acc.phone_number,
                'created_at': acc.created_at,
                'updated_at': acc.updated_at,
                'is_active': acc.is_active
            } for acc in accounts])
        except Exception as e:
            logger.error(f"获取账号列表失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts', methods=['POST'])
    def create_account():
        """创建账号"""
        try:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
            phone_number = data.get('phone_number', '+447700900000')  # 默认英国号码

            if not email or not password:
                return jsonify({'error': '邮箱和密码不能为空'}), 400

            account = db_manager.create_account(email, password, phone_number)
            return jsonify({
                'id': account.id,
                'email': account.email,
                'phone_number': account.phone_number,
                'created_at': account.created_at,
                'is_active': account.is_active
            }), 201

        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"创建账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts/<int:account_id>', methods=['PUT'])
    def update_account(account_id):
        """更新账号"""
        try:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
            phone_number = data.get('phone_number')

            success = db_manager.update_account(account_id, email, password, phone_number)
            if success:
                account = db_manager.get_account_by_id(account_id)
                return jsonify({
                    'id': account.id,
                    'email': account.email,
                    'phone_number': account.phone_number,
                    'updated_at': account.updated_at,
                    'is_active': account.is_active
                })
            else:
                return jsonify({'error': '账号不存在'}), 404

        except Exception as e:
            logger.error(f"更新账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
    def delete_account(account_id):
        """删除账号"""
        try:
            success = db_manager.delete_account(account_id)
            if success:
                return jsonify({'message': '账号删除成功'})
            else:
                return jsonify({'error': '账号不存在'}), 404

        except Exception as e:
            logger.error(f"删除账号失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # 礼品卡管理API
    @app.route('/api/gift-cards', methods=['GET'])
    def get_gift_cards():
        """获取所有礼品卡"""
        try:
            status_filter = request.args.get('status')
            gift_cards = db_manager.get_all_gift_cards(status_filter=status_filter)
            return jsonify([{
                'id': card.id,
                'gift_card_number': card.gift_card_number,
                'status': card.status,
                'notes': card.notes,
                'created_at': card.created_at,
                'updated_at': card.updated_at,
                'is_active': card.is_active
            } for card in gift_cards])
        except Exception as e:
            logger.error(f"获取礼品卡列表失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards', methods=['POST'])
    def create_gift_card():
        """创建礼品卡"""
        try:
            data = request.get_json()
            gift_card_number = data.get('gift_card_number')
            status = data.get('status', GiftCardStatus.HAS_BALANCE.value)
            notes = data.get('notes', '')

            if not gift_card_number:
                return jsonify({'error': '礼品卡号不能为空'}), 400

            gift_card = db_manager.create_gift_card(gift_card_number, status, notes)
            return jsonify({
                'id': gift_card.id,
                'gift_card_number': gift_card.gift_card_number,
                'status': gift_card.status,
                'notes': gift_card.notes,
                'created_at': gift_card.created_at,
                'is_active': gift_card.is_active
            }), 201

        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"创建礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards/<int:card_id>', methods=['PUT'])
    def update_gift_card(card_id):
        """更新礼品卡"""
        try:
            data = request.get_json()
            gift_card_number = data.get('gift_card_number')
            status = data.get('status')
            notes = data.get('notes')

            success = db_manager.update_gift_card(card_id, gift_card_number, status, notes)
            if success:
                gift_card = db_manager.get_gift_card_by_id(card_id)
                return jsonify({
                    'id': gift_card.id,
                    'gift_card_number': gift_card.gift_card_number,
                    'status': gift_card.status,
                    'notes': gift_card.notes,
                    'updated_at': gift_card.updated_at,
                    'is_active': gift_card.is_active
                })
            else:
                return jsonify({'error': '礼品卡不存在'}), 404

        except Exception as e:
            logger.error(f"更新礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-cards/<int:card_id>', methods=['DELETE'])
    def delete_gift_card(card_id):
        """删除礼品卡"""
        try:
            success = db_manager.delete_gift_card(card_id)
            if success:
                return jsonify({'message': '礼品卡删除成功'})
            else:
                return jsonify({'error': '礼品卡不存在'}), 404

        except Exception as e:
            logger.error(f"删除礼品卡失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/gift-card-statuses', methods=['GET'])
    def get_gift_card_statuses():
        """获取礼品卡状态选项"""
        return jsonify([status.value for status in GiftCardStatus])

    @app.route('/api/statistics', methods=['GET'])
    def get_statistics():
        """获取统计信息"""
        try:
            stats = db_manager.get_statistics()
            return jsonify(stats)
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # 错误处理
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    # 存储到app上下文中，方便其他地方使用
    app.task_manager = task_manager
    app.websocket_handler = websocket_handler
    app.ip_service = ip_service
    
    return app, socketio

if __name__ == '__main__':
    config_name = os.environ.get('FLASK_CONFIG', 'development')
    app, socketio = create_app(config_name)
    
    logger.info("Starting Apple Bot System...")
    logger.info(f"Config: {config_name}")
    logger.info(f"Debug mode: {app.config['DEBUG']}")
    
    # 启动应用
    port = int(os.environ.get('PORT', 5001))  # 改为5001端口，支持环境变量配置
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )