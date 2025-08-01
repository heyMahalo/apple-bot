import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'apple-bot-secret-key-2024'
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    # Redis配置 (用于任务队列)
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Celery配置 (用于并行任务处理)
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # WebSocket配置
    SOCKETIO_ASYNC_MODE = 'eventlet'
    
    # 自动化配置
    MAX_CONCURRENT_TASKS = int(os.environ.get('MAX_CONCURRENT_TASKS', '3'))
    TASK_TIMEOUT = int(os.environ.get('TASK_TIMEOUT', '1800'))  # 30分钟
    USE_CELERY = os.environ.get('USE_CELERY', 'False').lower() == 'true'  # 🚀 禁用Celery以支持GUI显示
    
    # IP代理配置 (预留)
    PROXY_ROTATION_ENABLED = os.environ.get('PROXY_ROTATION_ENABLED', 'False').lower() == 'true'
    PROXY_API_URL = os.environ.get('PROXY_API_URL', '')
    
class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}