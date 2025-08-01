"""
Celery任务定义
处理Apple Bot的异步任务执行
"""
import asyncio
import logging
from celery import current_task
from celery_config import celery_app
# 延迟导入避免循环依赖
def get_task_dependencies():
    """延迟导入任务依赖"""
    from models.task import Task, TaskStatus
    from services.automation_service import AutomationService
    from services.ip_service import IPService
    import socketio
    return Task, TaskStatus, AutomationService, IPService, socketio

logger = logging.getLogger(__name__)

# 全局服务实例
automation_service = None
websocket_client = None

def get_automation_service():
    """获取自动化服务实例"""
    global automation_service
    if automation_service is None:
        # 获取依赖
        Task, TaskStatus, AutomationService, IPService, socketio = get_task_dependencies()
        ip_service = IPService(rotation_enabled=True)
        automation_service = AutomationService(ip_service=ip_service)
    return automation_service

def get_websocket_client():
    """获取WebSocket客户端实例"""
    global websocket_client
    if websocket_client is None:
        # 获取依赖
        Task, TaskStatus, AutomationService, IPService, socketio = get_task_dependencies()
        # 创建Socket.IO客户端连接到主应用
        websocket_client = socketio.SimpleClient()
        try:
            websocket_client.connect('http://localhost:5001')
            logger.info("✅ Celery WebSocket客户端连接成功")
        except Exception as e:
            logger.error(f"❌ Celery WebSocket客户端连接失败: {e}")
            websocket_client = None
    return websocket_client

def emit_task_event(event_name, data):
    """发送任务事件到前端 - 通过Redis发布订阅"""
    try:
        import redis
        import json

        # 连接Redis
        redis_client = redis.Redis.from_url('redis://localhost:6379/0')

        # 发布事件到Redis频道
        event_data = {
            'event': event_name,
            'data': data,
            'timestamp': logger.handlers[0].formatter.formatTime(logging.LogRecord('', 0, '', 0, '', (), None)) if logger.handlers else None
        }

        redis_client.publish('celery_events', json.dumps(event_data))
        logger.debug(f"📡 通过Redis发送事件: {event_name} -> {data}")

    except Exception as e:
        logger.error(f"❌ 发送事件失败: {e}")

@celery_app.task(bind=True, name='tasks.execute_apple_task')
def execute_apple_task(self, task_data):
    """
    执行Apple购买任务

    Args:
        task_data: 任务数据字典

    Returns:
        dict: 任务执行结果
    """
    # 获取依赖
    Task, TaskStatus, AutomationService, IPService, socketio = get_task_dependencies()

    task_id = task_data.get('id')
    logger.info(f"🚀 Celery开始执行任务: {task_id}")

    try:
        # 创建任务对象
        task = Task.from_dict(task_data)
        
        # 发送任务开始事件
        emit_task_event('task_status_update', {
            'task_id': task_id,
            'status': 'running',
            'progress': 0,
            'message': 'Celery任务已启动'
        })
        
        # 更新Celery任务状态
        self.update_state(
            state='PROGRESS',
            meta={'task_id': task_id, 'progress': 0, 'status': 'initializing'}
        )
        
        # 获取自动化服务
        automation = get_automation_service()
        
        # 🚀 使用现有的消息服务而不是自定义事件发布
        def get_message_service():
            """获取消息服务实例"""
            try:
                from services.message_service import get_message_service
                return get_message_service()
            except Exception as e:
                logger.error(f"❌ 获取消息服务失败: {e}")
                return None

        # 设置WebSocket处理器
        class CeleryWebSocketHandler:
            def __init__(self):
                self.message_service = get_message_service()

            def broadcast(self, event, data):
                """广播事件"""
                if self.message_service:
                    self.message_service.publish(event, data)
                else:
                    emit_task_event(event, data)

            def emit(self, event, data):
                """发送事件"""
                if self.message_service:
                    self.message_service.publish(event, data)
                else:
                    emit_task_event(event, data)

            def send_task_log(self, task_id, message, level="info"):
                """发送任务日志"""
                if self.message_service:
                    self.message_service.sync_task_log(task_id, level, message)
                else:
                    emit_task_event('task_log', {
                        'task_id': task_id,
                        'message': message,
                        'level': level,
                        'timestamp': None
                    })

            def send_step_update(self, task_id, step, status, progress, message):
                """发送步骤更新"""
                if self.message_service:
                    # 使用现有的消息服务
                    self.message_service.sync_task_status(task_id, status, progress, message)
                else:
                    # 回退到自定义事件发布
                    emit_task_event('step_update', {
                        'task_id': task_id,
                        'step': step,
                        'status': status,
                        'progress': progress,
                        'message': message
                    })

                    emit_task_event('task_status_update', {
                        'task_id': task_id,
                        'status': status,
                        'progress': progress,
                        'message': message
                    })

            def send_task_event(self, event_name, data):
                """发送任务事件 - 缺失的方法"""
                if self.message_service:
                    self.message_service.publish(event_name, data)
                else:
                    emit_task_event(event_name, data)

        automation.websocket_handler = CeleryWebSocketHandler()
        
        # 🚀 使用try-catch包装任务执行，避免异常传播到Celery
        try:
            result = asyncio.run(automation.execute_task(task))

            if result:
                # 任务成功完成
                emit_task_event('task_status_update', {
                    'task_id': task_id,
                    'status': 'completed',
                    'progress': 100,
                    'message': '任务执行成功'
                })

                self.update_state(
                    state='SUCCESS',
                    meta={'task_id': task_id, 'progress': 100, 'status': 'completed'}
                )

                logger.info(f"✅ Celery任务执行成功: {task_id}")
                return {'status': 'success', 'task_id': task_id, 'message': '任务执行成功'}
            else:
                # 任务执行失败（返回False）
                emit_task_event('task_status_update', {
                    'task_id': task_id,
                    'status': 'failed',
                    'progress': task.progress,
                    'message': '任务执行失败'
                })

                self.update_state(
                    state='SUCCESS',  # 🚀 重要：使用SUCCESS避免Celery异常处理
                    meta={'task_id': task_id, 'progress': task.progress, 'status': 'failed', 'result': 'failed'}
                )

                logger.error(f"❌ Celery任务执行失败: {task_id}")
                return {'status': 'failed', 'task_id': task_id, 'message': '任务执行失败'}

        except Exception as task_exception:
            # 任务执行过程中的异常
            error_msg = str(task_exception)
            logger.error(f"❌ 任务执行异常: {task_id} - {error_msg}")

            emit_task_event('task_status_update', {
                'task_id': task_id,
                'status': 'failed',
                'progress': getattr(task, 'progress', 0),
                'message': f'任务执行异常: {error_msg}'
            })

            self.update_state(
                state='SUCCESS',  # 🚀 重要：使用SUCCESS避免Celery异常处理
                meta={
                    'task_id': task_id,
                    'progress': getattr(task, 'progress', 0),
                    'status': 'failed',
                    'result': 'failed',
                    'error': error_msg
                }
            )

            return {'status': 'failed', 'task_id': task_id, 'error': error_msg}

    except Exception as outer_exception:
        # 🚀 最外层异常捕获（理论上不应该到达这里）
        error_msg = str(outer_exception)
        logger.error(f"❌ Celery外层异常: {task_id} - {error_msg}")

        # 确保返回成功状态，避免Celery异常处理
        return {
            'status': 'failed',
            'task_id': task_id,
            'error': f'外层异常: {error_msg}',
            'exc_type': type(outer_exception).__name__
        }

@celery_app.task(name='tasks.cleanup_task')
def cleanup_task(task_id):
    """
    清理任务资源

    Args:
        task_id: 任务ID
    """
    logger.info(f"🧹 Celery开始清理任务资源: {task_id}")

    try:
        # 获取依赖
        Task, TaskStatus, AutomationService, IPService, socketio = get_task_dependencies()

        automation = get_automation_service()
        if automation:
            # 异步清理资源
            asyncio.run(automation.cleanup_task(task_id, force_close=True))
            logger.info(f"✅ Celery任务资源清理完成: {task_id}")

        return {'status': 'success', 'task_id': task_id, 'message': '资源清理完成'}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Celery任务资源清理失败: {task_id} - {error_msg}")
        return {
            'status': 'failed',
            'task_id': task_id,
            'error': error_msg,
            'exc_type': type(e).__name__
        }

@celery_app.task(name='tasks.cancel_task')
def cancel_task(task_id):
    """
    取消任务执行
    
    Args:
        task_id: 任务ID
    """
    logger.info(f"⏸️ Celery取消任务: {task_id}")
    
    try:
        # 发送取消事件
        emit_task_event('task_status_update', {
            'task_id': task_id,
            'status': 'cancelled',
            'message': '任务已取消'
        })
        
        # 清理资源
        cleanup_task.delay(task_id)
        
        logger.info(f"✅ Celery任务取消完成: {task_id}")
        return {'status': 'success', 'task_id': task_id, 'message': '任务已取消'}
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Celery任务取消失败: {task_id} - {error_msg}")
      