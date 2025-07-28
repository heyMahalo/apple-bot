#!/bin/bash

# Apple Bot System 启动脚本

echo "🍎 Apple Bot System 启动脚本"
echo "=================================="

# 检查Python版本
python_version=$(python3 --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo "✅ Python版本: $python_version"
else
    echo "❌ Python3 未安装，请先安装Python 3.8+"
    exit 1
fi

# 检查Node.js版本
node_version=$(node --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo "✅ Node.js版本: $node_version"
else
    echo "❌ Node.js 未安装，请先安装Node.js 14+"
    exit 1
fi

echo ""
echo "🚀 开始启动系统..."

# 启动后端
echo "📦 启动后端服务..."
cd backend

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "🔧 创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装Python依赖
echo "📥 安装后端依赖..."
pip install -r requirements.txt

# 安装Playwright浏览器
echo "🌐 安装Playwright浏览器..."
playwright install

# 启动后端服务
echo "🎯 启动Flask后端..."
python app.py &
BACKEND_PID=$!

# 等待后端启动
sleep 5

cd ../frontend

# 安装前端依赖
if [ ! -d "node_modules" ]; then
    echo "📥 安装前端依赖..."
    npm install
fi

# 启动前端服务
echo "🎨 启动Vue前端..."
npm run serve &
FRONTEND_PID=$!

echo ""
echo "✅ 系统启动完成！"
echo "📍 后端服务: http://localhost:5001"
echo "📍 前端界面: http://localhost:8080"
echo ""
echo "按 Ctrl+C 停止服务"

# 等待用户中断
trap "echo ''; echo '🛑 正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait