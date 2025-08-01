#!/bin/bash
# Apple Bot System 完整启动脚本
# 启动Redis、Celery Worker和Flask应用

echo "🚀 启动Apple Bot System (Celery模式)"

# 检查Redis是否运行
echo "📡 检查Redis服务..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis未运行，请先启动Redis服务"
    echo "   macOS: brew services start redis"
    echo "   Linux: sudo systemctl start redis"
    exit 1
fi
echo "✅ Redis服务正常"

# 设置环境变量
export USE_CELERY=True
export REDIS_URL=redis://localhost:6379/0

# 创建日志目录
mkdir -p logs

# 启动Celery Worker (后台)
echo "🔄 启动Celery Worker..."
python start_celery.py worker > logs/celery_worker.log 2>&1 &
CELERY_PID=$!
echo "✅ Celery Worker已启动 (PID: $CELERY_PID)"

# 等待Celery Worker启动
sleep 3

# 启动Flask应用
echo "🌐 启动Flask应用..."
python app.py

# 清理：当Flask应用退出时，也停止Celery Worker
echo "🧹 正在清理进程..."
kill $CELERY_PID 2>/dev/null
echo "✅ 所有服务已停止"
