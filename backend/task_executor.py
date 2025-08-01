#!/usr/bin/env python3
"""
独立的任务执行器 - 在单独进程中运行以避免事件循环冲突
支持实时进度推送和智能步骤跳过
"""

import sys
import os
import json
import logging
import asyncio
import time
import re
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.task import Task, TaskStep, TaskStatus
from services.automation_service import AutomationService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TaskExecutor:
    """独立的任务执行器"""

    def __init__(self):
        self.automation_service = AutomationService()
        self.progress_callback = None

    def set_progress_callback(self, callback):
        """设置进度回调函数"""
        self.progress_callback = callback

    def _send_progress_update(self, task: Task):
        """发送进度更新 - 使用强制刷新确保实时性"""
        if self.progress_callback:
            self.progress_callback(task.to_dict())
        else:
            # 使用强制刷新的方式输出到stdout
            progress_data = {
                'type': 'progress',
                'data': task.to_dict()
            }
            # 强制刷新stdout和stderr
            sys.stdout.write(f"PROGRESS:{json.dumps(progress_data)}\n")
            sys.stdout.flush()
            sys.stderr.flush()

            # 额外的调试输出
            sys.stderr.write(f"DEBUG: Progress sent for task {task.id}: {task.progress}%\n")
            sys.stderr.flush()

    def _analyze_url(self, url: str) -> dict:
        """分析URL，判断是否包含完整的产品配置"""
        analysis = {
            'is_complete_url': False,
            'has_model': False,
            'has_size': False,
            'has_storage': False,
            'has_color': False,
            'skip_configuration': False
        }

        # 检查是否是完整的产品URL
        # 例如: https://www.apple.com/uk/shop/buy-iphone/iphone-15/6.7-inch-display-512gb-black
        pattern = r'/buy-iphone/([^/]+)/([^/]+)'
        match = re.search(pattern, url)

        if match:
            model_part = match.group(1)  # iphone-15
            config_part = match.group(2)  # 6.7-inch-display-512gb-black

            analysis['has_model'] = True

            # 检查是否包含尺寸信息
            if 'inch' in config_part:
                analysis['has_size'] = True

            # 检查是否包含存储信息
            storage_patterns = ['64gb', '128gb', '256gb', '512gb', '1tb']
            if any(storage in config_part.lower() for storage in storage_patterns):
                analysis['has_storage'] = True

            # 检查是否包含颜色信息
            color_patterns = ['black', 'white', 'blue', 'pink', 'yellow', 'green', 'purple', 'red']
            if any(color in config_part.lower() for color in color_patterns):
                analysis['has_color'] = True

            # 如果包含基本配置信息，则标记为完整URL（但不跳过整个配置步骤）
            if analysis['has_size'] and analysis['has_storage'] and analysis['has_color']:
                analysis['is_complete_url'] = True
                analysis['skip_configuration'] = True  # 这个标志用于跳过特定选项，不是整个步骤

        return analysis
    
    async def execute_task(self, task_data: dict) -> dict:
        """执行任务 - 直接调用AutomationService的完整流程"""
        try:
            # 从字典重建Task对象
            task = Task.from_dict(task_data)

            logger.info(f"开始执行任务: {task.id}")

            # 设置任务为运行状态
            task.status = TaskStatus.RUNNING
            task.add_log("🚀 任务开始执行", "info")
            self._send_progress_update(task)

            # 直接调用AutomationService的execute_task方法
            # 这个方法包含了完整的四阶段流程和实际的浏览器自动化操作
            success = await self.automation_service.execute_task(task)

            if success:
                if task.status == TaskStatus.WAITING_GIFT_CARD_INPUT:
                    # 任务在礼品卡输入页面暂停，不是真正的完成
                    task.add_log("⏳ 任务已暂停在礼品卡输入页面，等待用户操作", "info")
                else:
                    # 任务真正完成
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now()
                    task.add_log("🎉 任务执行成功", "success")
            else:
                task.status = TaskStatus.FAILED
                task.add_log("❌ 任务执行失败", "error")

            # 发送最终状态更新
            self._send_progress_update(task)

            logger.info(f"任务执行完成: {task.id}, 状态: {task.status}")

            return task.to_dict()

        except Exception as e:
            logger.error(f"任务执行失败: {str(e)}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.add_log(f"💥 任务执行失败: {str(e)}", "error")
            self._send_progress_update(task)
            return task.to_dict()
    
async def main():
    """主函数 - 从命令行参数获取任务数据并执行"""
    if len(sys.argv) != 2:
        print("Usage: python task_executor.py <task_json>")
        sys.exit(1)
    
    try:
        # 从命令行参数获取任务数据
        task_json = sys.argv[1]
        task_data = json.loads(task_json)
        
        # 创建执行器并执行任务
        executor = TaskExecutor()
        result = await executor.execute_task(task_data)
        
        # 输出结果
        print(json.dumps(result))
        
    except Exception as e:
        logger.error(f"执行器启动失败: {str(e)}")
        error_result = {
            'status': 'failed',
            'error_message': str(e)
        }
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    # 在新的事件循环中运行
    asyncio.run(main())
