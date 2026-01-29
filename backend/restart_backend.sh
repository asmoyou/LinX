#!/bin/bash

# Clean restart script for backend
# This ensures all Python cache is cleared and backend runs with latest code

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the backend directory
cd "$SCRIPT_DIR"

echo "📂 Working directory: $(pwd)"
echo ""
echo "🧹 Cleaning Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

echo ""
echo "🔍 Checking for processes on port 8000..."
PORT_PIDS=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PORT_PIDS" ]; then
    echo "⚠️  Found processes using port 8000: $PORT_PIDS"
    echo "🛑 Killing processes on port 8000..."
    echo "$PORT_PIDS" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

echo ""
echo "🛑 Killing ALL uvicorn and Python processes related to this project..."
pkill -9 -f "uvicorn.*api_gateway" 2>/dev/null || true
pkill -9 -f "python.*uvicorn" 2>/dev/null || true
pkill -9 -f "python.*api_gateway" 2>/dev/null || true
sleep 2

echo ""
echo "✅ Verifying port 8000 is free..."
PORT_CHECK=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PORT_CHECK" ]; then
    echo "❌ ERROR: Port 8000 is still in use by process: $PORT_CHECK"
    echo ""
    echo "Please manually kill the process:"
    echo "  kill -9 $PORT_CHECK"
    echo ""
    echo "Or use a different port by editing this script."
    exit 1
fi

echo "✅ Port 8000 is free!"
echo ""
echo "✅ Verifying no backend processes remain..."
REMAINING=$(ps aux | grep -E "(uvicorn|api_gateway)" | grep -v grep | grep -v "restart_backend")
if [ ! -z "$REMAINING" ]; then
    echo "⚠️  WARNING: Some backend processes still running:"
    echo "$REMAINING"
    echo ""
    read -p "Kill these processes? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "$REMAINING" | awk '{print $2}' | xargs kill -9 2>/dev/null || true
        sleep 1
    else
        echo "Please manually kill these processes and run this script again."
        exit 1
    fi
fi

echo "✅ All clean! Starting backend..."
echo ""
echo "📝 New Features:"
echo "   ✅ Agent cache with 30-minute TTL (auto-expire)"
echo "   ✅ Automatic cache cleanup on every access"
echo "   ✅ Cache invalidation on agent update/delete"
echo "   ✅ Manual cache clear: POST /api/v1/agents/cache/clear"
echo "   ✅ Cache stats: GET /api/v1/agents/cache/stats"
echo "   ✅ Dynamic cache size based on system memory"
echo ""
echo "📝 Debug logging enabled - watch for:"
echo "   - [STREAM] messages (what's sent to frontend)"
echo "   - Delta fields from LLM provider"
echo "   - Content type detection (thinking vs content)"
echo "   - Cache operations (hit/miss/cleanup/size)"
echo ""
echo "🚀 Starting backend with debug logging..."
echo ""

# Start backend with reload
echo "📝 Logs will be written to backend.log"
echo "   Use 'tail -f backend/backend.log' to monitor in real-time"
echo ""
.venv/bin/python -m uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug >> backend.log 2>&1
