#!/usr/bin/env python3
"""
IP切换功能测试脚本
测试礼品卡付款时的自动IP切换机制
"""

import asyncio
import logging
import sys
import os

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.ip_service import IPService, ProxyInfo, ProxyStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_ip_service_basic():
    """测试IP服务基本功能"""
    print("🧪 测试1: IP服务基本功能")
    
    # 初始化IP服务（启用测试模式）
    ip_service = IPService(rotation_enabled=True, test_mode=True)
    success = ip_service.initialize_proxy_pool()
    
    print(f"✅ 代理池初始化: {'成功' if success else '失败'}")
    
    # 获取代理池状态
    pool_status = ip_service.get_proxy_pool_status()
    print(f"📊 代理池状态: {pool_status}")
    
    # 获取当前IP信息
    current_ip = ip_service.get_current_ip_info()
    print(f"🌐 当前IP信息: {current_ip}")
    
    return ip_service

async def test_gift_card_ip_rotation():
    """测试礼品卡专用IP切换"""
    print("\n🧪 测试2: 礼品卡IP切换功能")
    
    ip_service = IPService(rotation_enabled=True, test_mode=True)
    ip_service.initialize_proxy_pool()
    
    # 模拟礼品卡号码  
    test_gift_cards = [
        "1234567890123456",
        "2345678901234567", 
        "3456789012345678"
    ]
    
    for i, card_number in enumerate(test_gift_cards, 1):
        print(f"\n--- 测试礼品卡 {i}: {card_number[:4]}**** ---")
        
        # 为礼品卡切换IP
        new_proxy = await ip_service.rotate_ip_for_gift_card(f"test_task_{i}", card_number)
        
        if new_proxy:
            print(f"✅ IP切换成功: {new_proxy.host}:{new_proxy.port} ({new_proxy.country})")
            
            # 获取该礼品卡的IP使用历史
            history = ip_service.get_gift_card_ip_history(card_number)
            print(f"📜 IP使用历史: {history}")
        else:
            print(f"❌ IP切换失败")
    
    # 测试同一张礼品卡重复使用
    print(f"\n--- 重复使用第一张礼品卡 ---")
    repeat_proxy = await ip_service.rotate_ip_for_gift_card("repeat_test", test_gift_cards[0])
    if repeat_proxy:
        print(f"✅ 重复使用IP切换成功: {repeat_proxy.host}:{repeat_proxy.port}")
    else:
        print("❌ 重复使用IP切换失败（预期行为，因为排除了已使用的IP）")

async def test_ip_blocking():
    """测试IP封禁功能"""
    print("\n🧪 测试3: IP封禁功能")
    
    ip_service = IPService(rotation_enabled=True, test_mode=True)
    ip_service.initialize_proxy_pool()
    
    # 获取第一个代理并标记为封禁
    if ip_service.proxy_pool:
        first_proxy = ip_service.proxy_pool[0]
        ip_address = f"{first_proxy.host}:{first_proxy.port}"
        
        print(f"🚫 标记IP为封禁: {ip_address}")
        ip_service.mark_ip_blocked(ip_address, "测试封禁")
        
        # 检查代理池状态
        pool_status = ip_service.get_proxy_pool_status()
        print(f"📊 封禁后代理池状态: {pool_status}")
        
        # 尝试切换IP（应该避开被封的IP）
        new_proxy = await ip_service.rotate_proxy(force=True)
        if new_proxy:
            new_ip = f"{new_proxy.host}:{new_proxy.port}"
            if new_ip != ip_address:
                print(f"✅ 成功避开被封IP，切换到: {new_ip}")
            else:
                print(f"❌ 未能避开被封IP")

def test_api_endpoints():
    """测试API接口"""
    print("\n🧪 测试4: API接口功能")
    
    import requests
    import json
    
    base_url = "http://localhost:5000"
    
    # 测试IP状态接口
    try:
        response = requests.get(f"{base_url}/api/ip/status")
        if response.status_code == 200:
            print("✅ IP状态接口测试成功")
            print(f"📊 响应数据: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        else:
            print(f"❌ IP状态接口测试失败: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("⚠️ 无法连接到服务器，请确保Flask应用正在运行")
    except Exception as e:
        print(f"❌ API测试异常: {str(e)}")

async def test_performance():
    """测试性能"""
    print("\n🧪 测试5: 性能测试")
    
    ip_service = IPService(rotation_enabled=True, test_mode=True)
    ip_service.initialize_proxy_pool()
    
    import time
    
    # 测试连续IP切换性能
    start_time = time.time()
    success_count = 0
    
    for i in range(5):
        new_proxy = await ip_service.rotate_proxy(force=True)
        if new_proxy:
            success_count += 1
        await asyncio.sleep(0.1)  # 小延迟模拟实际使用
    
    end_time = time.time()
    
    print(f"⏱️ 性能测试结果:")
    print(f"   - 总耗时: {end_time - start_time:.2f}秒")
    print(f"   - 成功切换: {success_count}/5")
    print(f"   - 平均每次: {(end_time - start_time)/5:.2f}秒")

async def main():
    """主测试函数"""
    print("🚀 开始IP切换功能测试")
    print("=" * 50)
    
    try:
        # 基本功能测试
        ip_service = await test_ip_service_basic()
        
        # 礼品卡IP切换测试
        await test_gift_card_ip_rotation()
        
        # IP封禁测试
        await test_ip_blocking()
        
        # API接口测试
        test_api_endpoints()
        
        # 性能测试
        await test_performance()
        
        print("\n" + "=" * 50)
        print("🎉 所有测试完成！")
        
        # 清理资源
        if 'ip_service' in locals():
            ip_service.cleanup()
            
    except Exception as e:
        print(f"❌ 测试过程中出现异常: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())