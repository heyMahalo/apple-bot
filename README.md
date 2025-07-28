# Apple Bot System

一个基于Flask + Vue的Apple自动购买系统，支持并行化任务处理和实时状态监控。

## 系统特性

- **并行化处理**: 支持多任务同时运行，最大化购买效率
- **实时监控**: WebSocket实时通信，前端实时显示任务进度
- **参数化配置**: 前端可视化配置产品选项
- **IP轮换**: 支持代理IP切换，避免被封禁
- **完整日志**: 详细的执行日志和错误追踪
- **现代化界面**: 基于Element Plus的响应式界面

## 技术栈

### 后端
- Flask - Web框架
- Flask-SocketIO - WebSocket通信
- Playwright - 浏览器自动化
- Celery - 异步任务队列
- Redis - 缓存和消息队列

### 前端
- Vue 3 - 前端框架
- Element Plus - UI组件库
- Vuex - 状态管理
- Socket.IO - WebSocket客户端
- Axios - HTTP请求

## 项目结构

```
apple_bot_system/
├── backend/                 # 后端代码
│   ├── app.py              # Flask主应用
│   ├── task_manager.py     # 任务管理器
│   ├── websocket_handler.py # WebSocket处理
│   ├── services/           # 服务层
│   │   ├── automation_service.py  # 自动化服务
│   │   └── ip_service.py          # IP切换服务
│   ├── models/             # 数据模型
│   │   └── task.py         # 任务模型
│   ├── config/             # 配置文件
│   │   └── config.py       # 应用配置
│   └── requirements.txt    # Python依赖
├── frontend/               # 前端代码
│   ├── src/
│   │   ├── App.vue         # 主应用组件
│   │   ├── main.js         # 入口文件
│   │   ├── components/     # Vue组件
│   │   │   ├── TaskList.vue      # 任务列表
│   │   │   ├── TaskConfig.vue    # 任务配置
│   │   │   ├── TaskStatus.vue    # 任务状态详情
│   │   │   └── SystemStatus.vue  # 系统状态
│   │   ├── services/       # 前端服务
│   │   │   └── websocket.js      # WebSocket客户端
│   │   └── store/          # Vuex状态管理
│   │       └── index.js    # 状态定义
│   ├── public/
│   └── package.json        # Node.js依赖
└── shared/                 # 共享代码
```

## 安装和运行

### 环境要求

- Python 3.8+
- Node.js 14+
- Redis (可选，用于任务队列)

### 后端设置

1. 进入后端目录：
```bash
cd apple_bot_system/backend
```

2. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 安装Playwright浏览器：
```bash
playwright install
```

5. 启动后端服务：
```bash
python app.py
```

后端服务将在 `http://localhost:5001` 启动。

### 前端设置

1. 进入前端目录：
```bash
cd apple_bot_system/frontend
```

2. 安装依赖：
```bash
npm install
```

3. 启动开发服务器：
```bash
npm run serve
```

前端应用将在 `http://localhost:8080` 启动。

## 使用指南

### 创建任务

1. 点击界面右上角的"创建任务"按钮
2. 填写任务基本信息：
   - 任务名称
   - Apple产品页面URL
3. 配置产品选项：
   - 产品型号
   - 存储容量
   - 颜色/材质
   - 以旧换新选项
   - 付款方式
   - AppleCare+选项
4. 设置高级选项：
   - 任务优先级
   - 是否使用代理IP
   - 礼品卡配置
5. 点击"创建任务"完成

### 管理任务

- **启动任务**: 点击任务列表中的"启动"按钮
- **取消任务**: 对运行中的任务点击"取消"按钮
- **查看详情**: 点击任务行或"详情"按钮查看完整信息
- **删除任务**: 点击"删除"按钮移除任务

### 实时监控

- 左侧菜单可筛选不同状态的任务
- 系统状态页面显示整体运行情况
- 任务详情页面显示实时执行日志
- WebSocket连接状态显示在顶部

## 高级功能

### IP轮换

系统支持通过代理服务进行IP轮换，特别在礼品卡应用阶段：

1. 在环境变量中配置代理API：
```bash
export PROXY_ROTATION_ENABLED=true
export PROXY_API_URL=http://your-proxy-api.com
```

2. 在创建任务时启用"使用代理"选项
3. 系统会在关键步骤自动切换IP

### 批量操作

- 支持多选任务进行批量启动/取消
- 可设置最大并发任务数限制
- 任务队列自动管理执行顺序

## 开发说明

### 扩展自动化逻辑

主要的自动化逻辑在 `backend/services/automation_service.py` 中：

- `navigate_to_product()` - 导航到产品页面
- `configure_product()` - 配置产品选项
- `add_to_bag()` - 添加到购物袋
- `checkout()` - 结账流程
- `apply_gift_card()` - 应用礼品卡
- `finalize_purchase()` - 完成购买

### 添加新的任务步骤

1. 在 `models/task.py` 的 `TaskStep` 枚举中添加新步骤
2. 在 `automation_service.py` 中实现具体逻辑
3. 在前端组件中添加对应的显示文本

### 自定义产品配置

在 `backend/app.py` 的 `/api/config/product-options` 接口中修改返回的选项数据。

## 注意事项

⚠️ **合规使用**: 本系统仅用于学习和研究目的，请遵守Apple网站的使用条款。

⚠️ **频率控制**: 建议设置合理的延迟和间隔，避免对服务器造成过大压力。

⚠️ **账户安全**: 不要在代码中硬编码敏感信息，使用环境变量管理配置。

## 故障排除

### 常见问题

1. **WebSocket连接失败**
   - 检查后端服务是否正常启动
   - 确认防火墙设置
   - 检查CORS配置

2. **Playwright初始化失败**
   - 确保已运行 `playwright install`
   - 检查系统依赖是否完整

3. **任务执行失败**
   - 查看任务详情中的错误日志
   - 检查目标网站是否有变化
   - 验证网络连接

### 日志查看

- 后端日志：`backend/app.log`
- 前端控制台：浏览器开发者工具
- 任务日志：任务详情页面

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 许可证

MIT License