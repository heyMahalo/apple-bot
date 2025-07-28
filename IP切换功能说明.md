# IP切换功能使用说明

## 功能概述

为苹果自动化系统添加了智能IP切换功能，专门用于礼品卡付款时自动切换IP地址，避免同一张礼品卡在同一IP下被重复使用而导致封禁。

## 核心功能

### 1. 智能IP池管理
- **代理池初始化**: 支持从API或配置文件加载代理列表
- **代理状态监控**: 跟踪每个代理的可用性、成功率、响应时间
- **失败代理处理**: 自动标记失败的代理，避免重复使用

### 2. 礼品卡专用IP切换
- **防重复使用**: 每张礼品卡会记录已使用的IP，避免重复
- **智能排除机制**: 自动排除已被封禁或已使用过的IP
- **使用限制**: 每个IP最多使用指定数量的礼品卡（默认2张）

### 3. 自动封禁检测
- **错误识别**: 自动检测礼品卡被拒绝的情况
- **IP标记**: 将导致礼品卡被拒绝的IP标记为被封禁
- **冷却机制**: 被封禁的IP进入24小时冷却期

## 使用方法

### 启动系统
```bash
# 进入项目目录
cd apple_bot_system

# 启动后端服务
cd backend
python app.py

# 或使用完整启动脚本
./start.sh
```

### API接口

#### 获取IP状态
```bash
GET /api/ip/status
```

#### 手动轮换IP
```bash
POST /api/system/rotate-ip
```

#### 为礼品卡轮换IP
```bash
POST /api/ip/rotate-for-gift-card
Content-Type: application/json

{
  "task_id": "task_123",
  "gift_card_number": "1234567890123456"
}
```

#### 手动封禁IP
```bash
POST /api/ip/block
Content-Type: application/json

{
  "ip_address": "192.168.1.100:8080",
  "reason": "Manual block"
}
```

#### 获取礼品卡IP历史
```bash
GET /api/ip/gift-card-history/{gift_card_number}
```

#### IP设置管理
```bash
# 获取设置
GET /api/ip/settings

# 更新设置
PUT /api/ip/settings
Content-Type: application/json

{
  "rotation_enabled": true,
  "gift_card_rotation_enabled": true,
  "max_gift_card_per_ip": 2,
  "rotation_interval": 300
}
```

## 工作流程

### 礼品卡付款时的IP切换流程

1. **检测礼品卡**: 系统检测到需要应用礼品卡
2. **查询历史**: 检查该礼品卡的IP使用历史
3. **选择新IP**: 从代理池中选择未使用过该礼品卡的IP
4. **验证代理**: 验证选中代理的可用性
5. **切换IP**: 重新创建浏览器上下文使用新代理
6. **重新加载**: 使用新IP重新加载当前页面
7. **应用礼品卡**: 继续正常的礼品卡应用流程
8. **记录使用**: 将该IP与礼品卡的使用关系记录到历史中

## 测试功能

运行测试脚本验证IP切换功能：

```bash
python test_ip_rotation.py
```

测试包括：IP服务基本功能、礼品卡IP切换、封禁机制、API接口、性能测试。

## 配置选项

- `rotation_enabled`: 是否启用IP轮换
- `gift_card_rotation_enabled`: 是否启用礼品卡专用IP切换
- `max_gift_card_per_ip`: 每个IP最多使用的礼品卡数量（默认2张）
- `rotation_interval`: IP轮换间隔时间（默认300秒）