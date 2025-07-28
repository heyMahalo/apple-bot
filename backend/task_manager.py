import threading
import subprocess
import json
import os
import sys
from typing import Dict, List, Optional
from datetime import datetime
import logging

from models.task import Task, TaskStatus, TaskStep, GiftCard

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, max_workers: int = 3):
        self.tasks: Dict[str, Task] = {}
        self.max_workers = max_workers
        self.running_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        
    def create_task(self, task_config) -> Task:
        """创建新任务"""
        task = Task(
            id=None,  # 自动生成UUID
            config=task_config
        )
        
        with self._lock:
            self.tasks[task.id] = task
            
        logger.info(f"Created task {task.id}: {task.config.name}")
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_active_tasks(self) -> List[Task]:
        """获取活跃任务（运行中或等待中）"""
        return [task for task in self.tasks.values() 
                if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]]
    
    def start_task(self, task_id: str, websocket_handler=None) -> bool:
        """启动任务"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return False
            
        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task {task_id} is not in pending status")
            return False
        
        # 检查并发限制
        running_count = len([t for t in self.tasks.values() if t.status == TaskStatus.RUNNING])
        if running_count >= self.max_workers:
            logger.warning(f"Maximum concurrent tasks ({self.max_workers}) reached")
            return False
        
        # 更新任务状态
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.add_log(f"任务开始执行")

        # 通知WebSocket客户端任务状态更新
        if websocket_handler:
            websocket_handler.broadcast('task_update', task.to_dict())

        # 在独立进程中执行任务
        success = self._start_task_process(task, websocket_handler)

        if success:
            logger.info(f"Started task {task_id}")
            return True
        else:
            task.status = TaskStatus.FAILED
            task.add_log("启动任务进程失败", "error")
            return False
    
    def cancel_task(self, task_id: str, websocket_handler=None) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            # 终止运行中的进程
            if task_id in self.running_processes:
                try:
                    process = self.running_processes[task_id]
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                except Exception as e:
                    logger.error(f"终止任务进程失败: {str(e)}")
                finally:
                    if task_id in self.running_processes:
                        del self.running_processes[task_id]

            task.status = TaskStatus.CANCELLED
            task.add_log("任务已取消")

            # 通知WebSocket客户端任务状态更新
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())

            logger.info(f"Cancelled task {task_id}")

        return True

    def delete_task(self, task_id: str, websocket_handler=None) -> bool:
        """删除任务"""
        task = self.get_task(task_id)
        if not task:
            return False

        # 如果任务正在运行，先取消它
        if task.status == TaskStatus.RUNNING:
            self.cancel_task(task_id, websocket_handler)

        # 从任务列表中移除
        if task_id in self.tasks:
            del self.tasks[task_id]

            # 通知WebSocket客户端任务已删除
            if websocket_handler:
                websocket_handler.broadcast('task_deleted', {'task_id': task_id})

            logger.info(f"Deleted task {task_id}")
            return True

        return False

    def _start_task_process(self, task: Task, websocket_handler=None) -> bool:
        """在独立进程中启动任务"""
        try:
            # 获取task_executor.py的路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            executor_path = os.path.join(current_dir, 'task_executor.py')

            # 将任务数据序列化为JSON
            task_json = json.dumps(task.to_dict())

            # 启动独立进程 - 使用无缓冲模式确保实时输出
            process = subprocess.Popen(
                [sys.executable, '-u', executor_path, task_json],  # -u 参数强制无缓冲
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # 无缓冲
                cwd=current_dir,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}  # 环境变量确保无缓冲
            )

            # 存储进程引用
            self.running_processes[task.id] = process

            # 在后台线程中监控进程
            monitor_thread = threading.Thread(
                target=self._monitor_task_process,
                args=(task, process, websocket_handler),
                daemon=True
            )
            monitor_thread.start()

            return True

        except Exception as e:
            logger.error(f"启动任务进程失败: {str(e)}")
            return False

    def _monitor_task_process(self, task: Task, process: subprocess.Popen, websocket_handler=None):
        """监控任务进程 - 支持实时进度读取"""
        import select
        import time

        try:
            logger.info(f"开始监控任务进程: {task.id}")

            # 实时读取进程输出
            while True:
                # 检查进程是否还在运行
                if process.poll() is not None:
                    logger.info(f"任务进程 {task.id} 已结束")
                    break

                # 使用select进行非阻塞读取（仅在Unix系统上）
                try:
                    ready, _, _ = select.select([process.stdout], [], [], 0.1)
                    if ready:
                        line = process.stdout.readline()
                        if line:
                            line = line.strip()
                            if line:
                                logger.debug(f"任务 {task.id} 输出: {line}")
                                self._process_output_line(line, task, websocket_handler)
                    else:
                        # 没有输出时短暂休眠
                        time.sleep(0.1)
                except (OSError, ValueError):
                    # 在Windows上或其他不支持select的情况下，使用阻塞读取
                    line = process.stdout.readline()
                    if line:
                        line = line.strip()
                        if line:
                            logger.debug(f"任务 {task.id} 输出: {line}")
                            self._process_output_line(line, task, websocket_handler)
                    else:
                        time.sleep(0.1)


            # 进程结束，读取最终结果
            remaining_output, stderr = process.communicate()

            # 清理进程引用
            if task.id in self.running_processes:
                del self.running_processes[task.id]

            if process.returncode == 0:
                # 进程成功完成，尝试解析最终结果
                try:
                    # 查找最后的JSON结果
                    lines = remaining_output.split('\n') if remaining_output else []
                    final_result = None

                    for line in reversed(lines):
                        line = line.strip()
                        if line and not line.startswith('PROGRESS:'):
                            try:
                                final_result = json.loads(line)
                                break
                            except json.JSONDecodeError:
                                continue

                    if final_result:
                        updated_task = Task.from_dict(final_result)

                        # 更新最终状态
                        task.status = updated_task.status
                        task.progress = updated_task.progress
                        task.current_step = updated_task.current_step
                        task.completed_at = updated_task.completed_at
                        task.error_message = updated_task.error_message
                        task.logs = updated_task.logs

                    logger.info(f"任务 {task.id} 执行完成，状态: {task.status}")

                except Exception as e:
                    logger.error(f"解析最终结果失败: {str(e)}")
                    if task.status == TaskStatus.RUNNING:
                        task.status = TaskStatus.FAILED
                        task.add_log(f"解析最终结果失败: {str(e)}", "error")
            else:
                # 进程执行失败
                logger.error(f"任务进程执行失败: {stderr}")
                task.status = TaskStatus.FAILED
                task.add_log(f"任务进程执行失败: {stderr}", "error")

            # 发送最终状态更新
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())

        except Exception as e:
            logger.error(f"监控任务进程失败: {str(e)}")
            task.status = TaskStatus.FAILED
            task.add_log(f"监控任务进程失败: {str(e)}", "error")

            # 通知WebSocket客户端
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())

    def _process_output_line(self, line: str, task: Task, websocket_handler=None):
        """处理进程输出行"""
        try:
            # 处理进度更新
            if line.startswith('PROGRESS:'):
                progress_json = line[9:]  # 移除 'PROGRESS:' 前缀
                progress_data = json.loads(progress_json)

                if progress_data['type'] == 'progress':
                    updated_task_data = progress_data['data']

                    # 更新任务状态
                    task.status = TaskStatus(updated_task_data['status'])
                    task.progress = updated_task_data.get('progress', 0)
                    task.current_step = TaskStep(updated_task_data['current_step']) if updated_task_data.get('current_step') else None
                    task.error_message = updated_task_data.get('error_message')
                    task.logs = updated_task_data.get('logs', [])

                    # 实时通知WebSocket客户端
                    if websocket_handler:
                        websocket_handler.broadcast('task_update', task.to_dict())

                    logger.info(f"📊 任务 {task.id} 进度更新: {task.progress}% - {task.current_step}")

            elif line.startswith('WEBSOCKET_EVENT:'):
                # 处理WebSocket事件 - 新增功能
                event_json = line[16:]  # 移除 'WEBSOCKET_EVENT:' 前缀
                event_data = json.loads(event_json)
                
                if websocket_handler and event_data.get('type') == 'websocket_event':
                    event_name = event_data.get('event')
                    event_payload = event_data.get('data', {})
                    
                    # 转发事件给WebSocket客户端
                    websocket_handler.broadcast(event_name, event_payload)
                    logger.info(f"🎯 WebSocket事件转发: {event_name} for task {task.id}")

            elif line.startswith('DEBUG:'):
                # 调试信息
                logger.debug(f"任务 {task.id} 调试: {line[6:]}")
            else:
                # 普通日志输出
                logger.info(f"任务 {task.id} 输出: {line}")

        except json.JSONDecodeError as e:
            logger.warning(f"解析进度数据失败: {str(e)}, 原始数据: {line}")
        except Exception as e:
            logger.error(f"处理输出行失败: {str(e)}, 原始数据: {line}")

    def cleanup(self):
        """清理资源"""
        # 终止所有运行中的进程
        for task_id, process in self.running_processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                logger.error(f"清理进程 {task_id} 失败: {str(e)}")

        self.running_processes.clear()

    def reset_and_restart_task(self, task_id: str, websocket_handler=None) -> bool:
        """重置并重新启动任务"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found for reset and restart")
            return False
        
        try:
            # 如果任务正在运行，先取消它
            if task.status == TaskStatus.RUNNING:
                logger.info(f"Cancelling running task {task_id} before reset")
                self.cancel_task(task_id, websocket_handler)
                # 等待取消完成
                import time
                time.sleep(1)
            
            # 重置任务状态和数据
            logger.info(f"Resetting task {task_id} to initial state")
            task.status = TaskStatus.PENDING
            task.progress = 0
            task.current_step = None
            task.started_at = None
            task.completed_at = None
            task.error_message = None
            task.logs = []
            
            # 清除礼品卡错误和余额错误
            if hasattr(task, 'gift_card_errors'):
                task.gift_card_errors = []
            if hasattr(task, 'balance_error'):
                task.balance_error = None
            
            task.add_log("任务已重置，准备重新启动")
            
            # 通知WebSocket客户端任务已重置
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())
            
            # 重新启动任务
            logger.info(f"Restarting task {task_id}")
            success = self.start_task(task_id, websocket_handler)
            
            if success:
                logger.info(f"Successfully reset and restarted task {task_id}")
                return True
            else:
                logger.error(f"Failed to restart task {task_id} after reset")
                task.add_log("重启任务失败", "error")
                if websocket_handler:
                    websocket_handler.broadcast('task_update', task.to_dict())
                return False
                
        except Exception as e:
            logger.error(f"Error resetting and restarting task {task_id}: {str(e)}")
            task.status = TaskStatus.FAILED
            task.add_log(f"重置任务失败: {str(e)}", "error")
            if websocket_handler:
                websocket_handler.broadcast('task_update', task.to_dict())
            return False