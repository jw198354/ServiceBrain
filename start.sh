#!/bin/bash

# ServiceBrain 启动脚本

echo "🚀 Starting ServiceBrain..."

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

# 检查 Node
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found"
    exit 1
fi

# 启动后端
echo "📦 Starting backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit backend/.env and set your LLM_API_KEY"
fi

pip install -r requirements.txt > /dev/null 2>&1

# 创建数据目录
mkdir -p data knowledge

# 后台启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"

cd ..

# 启动前端
echo "🎨 Starting frontend..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

npm run dev &
FRONTEND_PID=$!
echo "✅ Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "🎉 ServiceBrain is running!"
echo "📱 Frontend: http://localhost:5173"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# 等待中断
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '👋 Stopped'; exit 0" INT
