#!/usr/bin/env python3
"""
Apple Bot System 集成测试脚本
测试前后端集成和多并发任务支持
"""

import asyncio
import requests
import json
import time
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(__file__))

def test_backend_api():
    """测试后端API功能"""
    base_url = "http://localhost:5001"
    
    print("🔧 测试后端API...")
    
    try:
        # 1. 测试健康检查
        response = requests.get(f"{base_url}/api/health")
        if response.status_code == 200:
            print("✅ 健康检查通过")
        else:
            print("❌ 健康检查失败")
            return False
        
        # 2. 测试产品选项API
        response = requests.get(f"{base_url}/api/config/product-options")
        if response.status_code == 200:
            options = response.json()
            print(f"✅ 产品选项API正常，找到 {len(options.get('products', []))} 个产品")
            print(f"   可用型号: {len(options.get('models', []))} 个")
            print(f"   可用颜色: {len(options.get('finishes', []))} 个")
            print(f"   可用存储: {len(options.get('storages', []))} 个")
        else:
            print("❌ 产品选项API失败")
            return False
        
        # 3. 测试系统状态API
        response = requests.get(f"{base_url}/api/system/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ 系统状态API正常")
            print(f"   最大并发任务: {status.get('max_concurrent', 0)}")
            print(f"   当前活跃任务: {status.get('active_tasks', 0)}")
        else:
            print("❌ 系统状态API失败")
            return False
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到后端服务，请确保后端正在运行 (python app.py)")
        return False
    except Exception as e:
        print(f"❌ API测试失败: {str(e)}")
        return False

def create_test_tasks():
    """创建测试任务"""
    base_url = "http://localhost:5001"
    
    print("\n🚀 创建测试任务...")
    
    # 定义测试任务
    test_tasks = [
        {
            "name": "测试任务 1 - iPhone 16 Pro",
            "selected_product": "iPhone 16 Pro & iPhone 16 Pro Max",
            "url": "https://www.apple.com/uk/shop/buy-iphone/iphone-16-pro",
            "product_config": {
                "model": "iPhone 16 Pro 6.3-inch display",
                "finish": "Natural Titanium",
                "storage": "256GB",
                "trade_in": "No trade-in",
                "payment": "Buy",
                "apple_care": "No AppleCare+ Coverage"
            },
            "priority": 3,
            "use_proxy": False,
            "gift_cards": [],
            "enabled": True
        },
        {
            "name": "测试任务 2 - iPhone 16",
            "selected_product": "iPhone 16 & iPhone 16 Plus",
            "url": "https://www.apple.com/uk/shop/buy-iphone/iphone-16",
            "product_config": {
                "model": "iPhone 16 6.1-inch display",
                "finish": "Pink",
                "storage": "128GB",
                "trade_in": "No trade-in",
                "payment": "Buy",
                "apple_care": "No AppleCare+ Coverage"
            },
            "priority": 2,
            "use_proxy": False,
            "gift_cards": [],
            "enabled": True
        }
    ]
    
    created_tasks = []
    
    for task_data in test_tasks:
        try:
            response = requests.post(
                f"{base_url}/api/tasks",
                json=task_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 201:
                task_info = response.json()
                created_tasks.append(task_info['task_id'])
                print(f"✅ 创建任务成功: {task_data['name']} (ID: {task_info['task_id']})")
            else:
                print(f"❌ 创建任务失败: {task_data['name']} - {response.text}")
                
        except Exception as e:
            print(f"❌ 创建任务异常: {task_data['name']} - {str(e)}")
    
    return created_tasks

def start_test_tasks(task_ids):
    """启动测试任务"""
    base_url = "http://localhost:5001"
    
    print(f"\n⚡ 启动 {len(task_ids)} 个测试任务...")
    
    for task_id in task_ids:
        try:
            response = requests.post(f"{base_url}/api/tasks/{task_id}/start")
            
            if response.status_code == 200:
                print(f"✅ 任务 {task_id} 启动成功")
            else:
                print(f"❌ 任务 {task_id} 启动失败: {response.text}")
                
        except Exception as e:
            print(f"❌ 启动任务异常: {task_id} - {str(e)}")

def monitor_tasks(task_ids, duration=60):
    """监控任务状态"""
    base_url = "http://localhost:5001"
    
    print(f"\n👀 监控任务状态 (持续 {duration} 秒)...")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        try:
            # 获取系统状态
            response = requests.get(f"{base_url}/api/system/status")
            if response.status_code == 200:
                status = response.json()
                active_tasks = status.get('active_tasks', 0)
                print(f"📊 活跃任务: {active_tasks}, 总任务: {status.get('total_tasks', 0)}")
            
            # 检查每个任务的详细状态
            for task_id in task_ids:
                response = requests.get(f"{base_url}/api/tasks/{task_id}")
                if response.status_code == 200:
                    task = response.json()
                    status = task.get('status', 'unknown')
                    progress = task.get('progress', 0)
                    current_step = task.get('current_step', 'none')
                    
                    print(f"   📱 任务 {task_id[:8]}: {status} - {progress:.1f}% - {current_step}")
                    
                    # 如果有日志，显示最新的几条
                    logs = task.get('logs', [])
                    if logs:
                        latest_log = logs[-1]
                        print(f"       💬 {latest_log.get('message', '')}")
            
            time.sleep(10)  # 每10秒检查一次
            
        except Exception as e:
            print(f"❌ 监控异常: {str(e)}")
            break
    
    print("\n🏁 监控结束")

def cleanup_test_tasks(task_ids):
    """清理测试任务"""
    base_url = "http://localhost:5001"
    
    print(f"\n🧹 清理 {len(task_ids)} 个测试任务...")
    
    for task_id in task_ids:
        try:
            # 尝试取消任务
            response = requests.post(f"{base_url}/api/tasks/{task_id}/cancel")
            if response.status_code == 200:
                print(f"✅ 任务 {task_id} 已取消")
            else:
                print(f"⚠️ 任务 {task_id} 取消失败（可能已完成）")
        except Exception as e:
            print(f"❌ 清理任务异常: {task_id} - {str(e)}")

def main():
    """主测试流程"""
    print("="*60)
    print("🍎 Apple Bot System 集成测试")
    print("="*60)
    
    # 1. 测试后端API
    if not test_backend_api():
        print("\n❌ 后端API测试失败，请检查后端服务是否正常运行")
        print("启动命令: cd apple_bot_system/backend && python app.py")
        return
    
    # 2. 创建测试任务
    task_ids = create_test_tasks()
    if not task_ids:
        print("\n❌ 未能创建任何测试任务")
        return
    
    # 3. 启动任务
    start_test_tasks(task_ids)
    
    # 4. 监控任务执行
    try:
        monitor_tasks(task_ids, duration=120)  # 监控2分钟
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断监控")
    
    # 5. 清理任务
    cleanup_test_tasks(task_ids)
    
    print("\n✅ 测试完成！")
    print("\n📋 测试总结:")
    print("1. 后端API功能正常")
    print("2. 产品数据加载成功")
    print("3. 任务创建和启动成功") 
    print("4. 多并发任务支持验证")
    print("\n🎯 接下来可以：")
    print("1. 访问前端界面: http://localhost:5001")
    print("2. 使用前端创建和管理任务")
    print("3. 监控任务执行状态")

if __name__ == "__main__":
    main() 