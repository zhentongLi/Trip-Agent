#!/bin/bash
# 一键启动旅行规划助手（后端 + 前端）

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "========================================"
echo "  🗺  旅行规划助手 启动脚本"
echo "========================================"
echo ""

# 杀掉旧进程
pkill -f "uvicorn app.api.main" 2>/dev/null && echo "stopped old backend" || true

# ---- 后端 ----
echo "▶ 启动后端 (port 8000)..."
cd "$BACKEND_DIR"
nohup conda run -n trip-agent uvicorn app.api.main:app \
    --host 0.0.0.0 --port 8000 --reload \
    > "$BACKEND_DIR/logs/startup.log" 2>&1 &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID (日志: backend/logs/startup.log)"

# 等待后端就绪
echo "  等待后端启动..."
for i in {1..15}; do
    if curl -sf http://localhost:8000/api/trip/health > /dev/null 2>&1; then
        echo "  ✅ 后端已就绪"
        break
    fi
    sleep 1
    if [ $i -eq 15 ]; then
        echo "  ⚠️  后端启动超时，请检查日志: backend/logs/startup.log"
    fi
done

# ---- 前端 ----
echo ""
echo "▶ 启动前端 (port 5173)..."
cd "$FRONTEND_DIR"
nohup npm run dev > /tmp/trip-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  前端 PID: $FRONTEND_PID (日志: /tmp/trip-frontend.log)"

echo ""
echo "========================================"
echo "  访问地址: http://localhost:5173"
echo "  API 文档: http://localhost:8000/docs"
echo "  停止服务: pkill -f 'uvicorn app.api.main'; pkill -f 'vite'"
echo "========================================"
