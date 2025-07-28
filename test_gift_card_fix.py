#!/usr/bin/env python3
"""
测试礼品卡数据处理修复
"""

# 模拟前端发送的数据
frontend_data = {
    'name': '测试任务',
    'url': 'https://www.apple.com/uk/shop/buy-iphone/test',
    'gift_cards': [
        {
            'gift_card_number': 'TESTCARD001',
            'status': '有额度'
        },
        {
            'gift_card_number': 'TESTCARD002', 
            'status': '0余额'
        }
    ],
    'account_config': {
        'email': 'test@example.com',
        'password': 'password',
        'phone_number': '07700900000'
    },
    'product_config': {
        'model': 'iPhone 16 Pro',
        'finish': 'Natural Titanium',
        'storage': '256GB'
    }
}

# 模拟WebSocket处理逻辑
def test_gift_card_processing():
    print("🧪 测试礼品卡数据处理...")
    
    # 模拟后端处理逻辑
    gift_cards = []
    
    frontend_gift_cards = frontend_data.get('gift_cards', [])
    if frontend_gift_cards and len(frontend_gift_cards) > 0:
        for card_data in frontend_gift_cards:
            if isinstance(card_data, dict):
                gift_card_number = card_data.get('gift_card_number', '')
                gift_card_status = card_data.get('status', 'has_balance')
                
                if gift_card_number:
                    # 模拟GiftCard对象
                    gift_card = {
                        'number': gift_card_number,
                        'expected_status': gift_card_status
                    }
                    gift_cards.append(gift_card)
                    print(f"✅ 添加礼品卡: {gift_card_number[:4]}**** (状态: {gift_card_status})")
    
    # 设置向后兼容的gift_card_code
    gift_card_code = gift_cards[0]['number'] if gift_cards else None
    
    print(f"📊 处理结果: {len(gift_cards)}张礼品卡")
    print(f"🔧 向后兼容代码: {gift_card_code}")
    
    return len(gift_cards) > 0

if __name__ == '__main__':
    success = test_gift_card_processing()
    print(f"🎯 测试结果: {'通过' if success else '失败'}")