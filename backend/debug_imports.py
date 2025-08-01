#!/usr/bin/env python3
"""
调试导入问题 - 逐步测试每个导入
"""

import sys
import time

def test_import(module_name, import_statement):
    """测试单个导入"""
    try:
        print(f"🔍 测试导入: {module_name}")
        start_time = time.time()
        
        exec(import_statement)
        
        end_time = time.time()
        print(f"✅ {module_name} 导入成功 ({end_time - start_time:.2f}s)")
        return True
    except Exception as e:
        print(f"❌ {module_name} 导入失败: {e}")
        return False

def main():
    print("🚀 开始逐步测试导入...")
    
    # 基础导入
    imports_to_test = [
        ("Flask基础", "from flask import Flask, request, jsonify, send_from_directory"),
        ("SocketIO", "from flask_socketio import SocketIO"),
        ("CORS", "from flask_cors import CORS"),
        ("基础库", "import logging, os, asyncio"),
        ("datetime", "from datetime import datetime"),
        
        # 项目导入
        ("TaskManager", "from task_manager import TaskManager"),
        ("基础消息服务", "from services.message_service import init_message_service, get_message_service"),
        ("AutomationService", "from services.automation_service import AutomationService"),
        ("IP服务", "from services.ip_service import IPService"),
        ("WebSocket处理器", "from websocket_handler import WebSocketHandler"),
        
        # SOTA服务（可能的问题源）
        ("SOTA消息服务", "from services.message_service_sota import init_sota_message_service, get_sota_message_service"),
        ("SocketIO网关", "from services.socketio_gateway import init_socketio_gateway, get_socketio_gateway"),
    ]
    
    failed_imports = []
    
    for name, import_stmt in imports_to_test:
        if not test_import(name, import_stmt):
            failed_imports.append(name)
            print(f"⚠️ 停止测试，{name} 导入失败")
            break
        time.sleep(0.5)  # 短暂延迟
    
    if failed_imports:
        print(f"\n❌ 发现问题导入: {failed_imports}")
    else:
        print("\n✅ 所有导入测试通过")
        
        # 测试Flask应用创建
        print("\n🔍 测试Flask应用创建...")
        try:
            start_time = time.time()
            
            app = Flask(__name__)
            app.config['SECRET_KEY'] = 'test-key'
            
            end_time = time.time()
            print(f"✅ Flask应用创建成功 ({end_time - start_time:.2f}s)")
            
            # 测试SocketIO创建
            print("🔍 测试SocketIO创建...")
            start_time = time.time()
            
            socketio = SocketIO(app, cors_allowed_origins="*")
            
            end_time = time.time()
            print(f"✅ SocketIO创建成功 ({end_time - start_time:.2f}s)")
            
        except Exception as e:
            print(f"❌ Flask/SocketIO创建失败: {e}")

if __name__ == "__main__":
    main()
