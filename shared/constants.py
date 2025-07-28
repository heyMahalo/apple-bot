# 共享常量定义

# 任务状态
TASK_STATUS = {
    'PENDING': 'pending',
    'RUNNING': 'running',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'CANCELLED': 'cancelled'
}

# 任务步骤
TASK_STEPS = {
    'INITIALIZING': 'initializing',
    'NAVIGATING': 'navigating',
    'CONFIGURING_PRODUCT': 'configuring_product',
    'ADDING_TO_BAG': 'adding_to_bag',
    'CHECKOUT': 'checkout',
    'APPLYING_GIFT_CARD': 'applying_gift_card',
    'FINALIZING': 'finalizing'
}

# WebSocket事件
WEBSOCKET_EVENTS = {
    # 连接事件
    'CONNECT': 'connect',
    'DISCONNECT': 'disconnect',
    
    # 任务事件
    'TASK_CREATED': 'task_created',
    'TASK_UPDATE': 'task_update',
    'TASK_DELETED': 'task_deleted',
    'CREATE_TASK': 'create_task',
    'START_TASK': 'start_task',
    'CANCEL_TASK': 'cancel_task',
    'DELETE_TASK': 'delete_task',
    
    # 系统事件
    'SYSTEM_STATUS': 'system_status',
    'GET_SYSTEM_STATUS': 'get_system_status',
    
    # 错误事件
    'ERROR': 'error'
}

# API端点
API_ENDPOINTS = {
    'HEALTH': '/api/health',
    'TASKS': '/api/tasks',
    'SYSTEM_STATUS': '/api/system/status',
    'ROTATE_IP': '/api/system/rotate-ip',
    'PRODUCT_OPTIONS': '/api/config/product-options'
}

# 默认配置
DEFAULT_CONFIG = {
    'MAX_CONCURRENT_TASKS': 3,
    'TASK_TIMEOUT': 1800,  # 30分钟
    'RETRY_DELAY': 3000,   # 3秒
    'MAX_RETRIES': 3
}