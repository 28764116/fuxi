#!/bin/bash

# 同时启动前后端开发服务器 + Celery worker

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# 步骤1: 清理旧进程（避免端口占用和任务冲突）
echo "🧹 清理旧进程..."
pkill -9 -f "celery -A worker" 2>/dev/null || true
pkill -9 -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# 步骤2: 清理旧的 Celery 任务
echo "🧹 清理旧任务..."
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"
python3 clear_tasks.py

# 步骤3: 启动后端 (FastAPI/uvicorn)
echo "🚀 启动后端服务..."
source venv/bin/activate 2>/dev/null || true
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
sleep 2

# 步骤4: 启动 Celery worker (异步任务处理)
echo "⚙️  启动 Celery worker..."
celery -A worker worker --loglevel=info --concurrency=1 &
CELERY_PID=$!

# 启动前端 (Vite)
echo "🚀 启动前端服务..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ 服务已启动:"
echo "   后端 API:    http://localhost:8000"
echo "   前端界面:    http://localhost:3000"
echo "   Celery:     运行中 (后台任务)"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获 Ctrl+C 并清理
cleanup() {
    echo ''
    echo '🛑 正在停止所有服务...'
    kill $BACKEND_PID $CELERY_PID $FRONTEND_PID 2>/dev/null
    sleep 1
    # 强制清理可能残留的进程
    pkill -9 -f "celery -A worker" 2>/dev/null || true
    pkill -9 -f "uvicorn app.main" 2>/dev/null || true
    echo '✅ 服务已停止'
    exit
}
trap cleanup INT TERM

# 等待子进程
wait
