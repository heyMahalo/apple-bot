#!/usr/bin/env python3
"""
简化版app.py - 用于诊断启动问题
"""

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import logging
import os
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    
    # 启用CORS
    CORS(app, origins=["http://localhost:8080"])
    
    # 创建SocketIO实例
    socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
    
    logger.info("✅ Flask和SocketIO初始化完成")
    
    # 基础路由
    @app.route('/', methods=['GET'])
    def index():
        """主页"""
        return jsonify({
            'message': 'Apple Bot System API - Simple Version',
            'version': '1.0.0',
            'status': 'running'
        })
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        })
    
    @app.route('/api/tasks', methods=['GET'])
    def get_tasks():
        """获取所有任务"""
        # 返回模拟数据
        return jsonify({
            'tasks': [
                {
                    'id': 'test-task-1',
                    'status': 'stage_1_product_config',
                    'progress': 25,
                    'current_step': 'stage_1_product_config',
                    'config': {
                        'name': '测试任务1',
                        'url': 'https://www.apple.com/uk/shop/buy-iphone/iphone-15'
                    },
                    'created_at': datetime.now().isoformat(),
                    'logs': []
                }
            ]
        })
    
    @app.route('/api/tasks', methods=['POST'])
    def create_task():
        """创建任务"""
        task_data = request.get_json()
        logger.info(f"收到创建任务请求: {task_data}")
        
        return jsonify({
            'success': True,
            'task_id': 'test-task-new',
            'message': '任务创建成功'
        })
    
    # Socket.IO事件
    @socketio.on('connect')
    def handle_connect():
        logger.info('✅ 客户端已连接')
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('❌ 客户端已断开')
    
    @socketio.on('create_task')
    def handle_create_task(data):
        logger.info(f'收到创建任务请求: {data}')
        socketio.emit('task_created', {'task_id': 'test-task', 'status': 'pending'})
    
    return app, socketio

if __name__ == '__main__':
    try:
        logger.info("🚀 启动简化版Apple Bot System...")
        
        app, socketio = create_app()
        
        logger.info("✅ 应用创建成功，开始启动服务器...")
        
        # 启动服务器
        socketio.run(
            app,
            host='0.0.0.0',
            port=5001,
            debug=False,
            allow_unsafe_werkzeug=True
        )
        
    except Exception as e:
        logger.error(f"❌ 应用启动失败: {e}")
        import traceback
        traceback.print_exc()
