"""
Celery配置文件
使用Redis作为消息代理和结果后端
"""
import os
from celery import Celery

# Redis配置
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# 创建Celery实例
def create_celery_app():
    """创建Celery应用实例"""
    celery = Celery('apple_bot_tasks')
    
    # 配置Celery
    celery.conf.update(
        # 消息代理配置
        broker_url=REDIS_URL,
        result_backend=REDIS_URL,

        # 🚀 任务自动发现
        include=['celery_tasks'],  # 包含任务模块
        
        # 任务序列化
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        
        # 任务路由
        task_routes={
            'tasks.execute_apple_task': {'queue': 'apple_tasks'},
            'tasks.cleanup_task': {'queue': 'cleanup'},
        },
        
        # 工作进程配置
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=1000,
        
        # 任务超时配置
        task_soft_time_limit=1800,  # 30分钟软超时
        task_time_limit=2400,       # 40分钟硬超时
        
        # 结果过期时间
        result_expires=3600,        # 1小时后过期
        
        # 任务重试配置
        task_default_retry_delay=60,
        task_max_retries=3,
        
        # 监控配置
        worker_send_task_events=True,
        task_send_sent_event=True,
        
        # 队列配置
        task_default_queue='default',
        task_queues={
            'apple_tasks': {
                'exchange': 'apple_tasks',
                'routing_key': 'apple_tasks',
            },
            'cleanup': {
                'exchange': 'cleanup',
                'routing_key': 'cleanup',
            },
        },
    )
    
    return celery

# 全局Celery实例
celery_app = create_celery_app()
