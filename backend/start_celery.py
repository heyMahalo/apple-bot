#!/usr/bin/env python3
"""
Celery Worker启动脚本
用于启动Celery工作进程处理Apple Bot任务
"""
import os
import sys
import logging
from celery_config import celery_app

# 🚀 重要：导入所有任务模块，确保任务被注册
import celery_tasks

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def start_celery_worker():
    """启动Celery Worker"""
    logger.info("🚀 启动Celery Worker...")
    
    # Celery Worker参数
    worker_args = [
        'worker',
        '--loglevel=info',
        '--concurrency=4',  # 🚀 增加并发数到4，避免任务阻塞
        '--queues=apple_tasks,cleanup,default',  # 监听的队列
        '--hostname=apple-bot-worker@%h',
        '--max-tasks-per-child=50',  # 🚀 减少每个子进程最大任务数，更频繁重启
        '--time-limit=2400',  # 任务硬超时（40分钟）
        '--soft-time-limit=1800',  # 任务软超时（30分钟）
    ]
    
    # 启动Worker
    celery_app.worker_main(worker_args)

def start_celery_beat():
    """启动Celery Beat调度器"""
    logger.info("📅 启动Celery Beat调度器...")
    
    beat_args = [
        'beat',
        '--loglevel=info',
        '--schedule-filename=celerybeat-schedule',
    ]
    
    celery_app.start(beat_args)

def start_celery_flower():
    """启动Celery Flower监控"""
    logger.info("🌸 启动Celery Flower监控...")
    
    flower_args = [
        'flower',
        '--port=5555',
        '--broker=redis://localhost:6379/0',
    ]
    
    celery_app.start(flower_args)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'worker':
            start_celery_worker()
        elif command == 'beat':
            start_celery_beat()
        elif command == 'flower':
            start_celery_flower()
        else:
            print("用法: python start_celery.py [worker|beat|flower]")
            sys.exit(1)
    else:
        # 默认启动Worker
        start_celery_worker()
