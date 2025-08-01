#!/usr/bin/env python3
"""
测试四阶段状态系统
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from models.task import Task, TaskStatus, TaskStep, TaskConfig, ProductConfig, AccountConfig

def test_task_status_conversion():
    """测试任务状态转换"""
    print("=== 测试任务状态转换 ===")
    
    # 创建测试任务配置
    product_config = ProductConfig(
        model="iPhone 15 Pro",
        finish="Natural Titanium",
        storage="256GB"
    )
    
    account_config = AccountConfig(
        email="test@example.com",
        password="test123",
        phone_number="07123456789"
    )
    
    task_config = TaskConfig(
        name="测试任务",
        url="https://www.apple.com/uk/shop/buy-iphone/iphone-15-pro",
        product_config=product_config,
        account_config=account_config
    )
    
    # 创建任务
    task = Task(id=None, config=task_config)
    print(f"初始状态: {task.status}")
    
    # 测试四个阶段的状态转换
    stages = [
        (TaskStatus.STAGE_1_PRODUCT_CONFIG, "阶段1：产品配置"),
        (TaskStatus.STAGE_2_ACCOUNT_LOGIN, "阶段2：账号登录"),
        (TaskStatus.STAGE_3_ADDRESS_PHONE, "阶段3：地址电话配置"),
        (TaskStatus.STAGE_4_GIFT_CARD, "阶段4：礼品卡配置"),
        (TaskStatus.WAITING_GIFT_CARD_INPUT, "等待礼品卡输入"),
        (TaskStatus.COMPLETED, "已完成")
    ]
    
    for status, description in stages:
        task.status = status
        task_dict = task.to_dict()
        print(f"状态: {task_dict['status']} - {description}")
        
        # 验证JSON序列化正常
        import json
        json_str = json.dumps(task_dict, ensure_ascii=False, indent=2)
        print(f"JSON长度: {len(json_str)} 字符")
    
    print("✅ 状态转换测试完成")

def test_step_enums():
    """测试步骤枚举"""
    print("\n=== 测试步骤枚举 ===")
    
    four_stage_steps = [
        TaskStep.STAGE_1_PRODUCT_CONFIG,
        TaskStep.STAGE_2_ACCOUNT_LOGIN,
        TaskStep.STAGE_3_ADDRESS_PHONE,
        TaskStep.STAGE_4_GIFT_CARD
    ]
    
    for step in four_stage_steps:
        print(f"步骤: {step.value}")
    
    print("✅ 步骤枚举测试完成")

if __name__ == "__main__":
    test_task_status_conversion()
    test_step_enums()
    print("\n🎉 所有测试通过！四阶段状态系统工作正常")