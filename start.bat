@echo off
chcp 65001 >nul

echo 🍎 Apple Bot System 启动脚本
echo ==================================

REM 检查Python版本
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装，请先安装Python 3.8+
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version') do echo ✅ Python版本: %%i
)

REM 检查Node.js版本
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js 未安装，请先安装Node.js 14+
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('node --version') do echo ✅ Node.js版本: %%i
)

echo.
echo 🚀 开始启动系统...

REM 启动后端
echo 📦 启动后端服务...
cd backend

REM 检查虚拟环境
if not exist "venv" (
    echo 🔧 创建Python虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装Python依赖
echo 📥 安装后端依赖...
pip install -r requirements.txt

REM 安装Playwright浏览器
echo 🌐 安装Playwright浏览器...
playwright install

REM 启动后端服务
echo 🎯 启动Flask后端...
start "Apple Bot Backend" cmd /k "python app.py"

REM 等待后端启动
timeout /t 5 /nobreak >nul

cd ..\frontend

REM 安装前端依赖
if not exist "node_modules" (
    echo 📥 安装前端依赖...
    npm install
)

REM 启动前端服务
echo 🎨 启动Vue前端...
start "Apple Bot Frontend" cmd /k "npm run serve"

echo.
echo ✅ 系统启动完成！
echo 📍 后端服务: http://localhost:5001
echo 📍 前端界面: http://localhost:8080
echo.
echo 服务已在新窗口中启动，可以关闭此窗口
pause