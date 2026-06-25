#!/usr/bin/env bash
# 一键启动全部服务（不用 Docker 时）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

start_one() {
  local name=$1 dir=$2 port=$3
  if lsof -i ":$port" >/dev/null 2>&1; then
    echo "✓ $name 已在端口 $port 运行"
    return
  fi
  echo "▶ 启动 $name (:$port)..."
  cd "$ROOT/$dir"
  [ -d .venv ] || python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -r requirements.txt
  if [ "$dir" = "tune-engine" ]; then
    python scripts/init_demo.py 2>/dev/null || true
    nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "$port" > /tmp/tune-engine.log 2>&1 &
  else
    nohup python server.py > "/tmp/${dir}.log" 2>&1 &
  fi
  deactivate 2>/dev/null || true
  cd "$ROOT"
}

start_one "tune-engine"  "tune-engine"  8100
start_one "check-mcp"    "check-mcp"    8200
start_one "run-log-mcp"  "run-log-mcp"  8300

sleep 2
echo ""
echo "服务地址："
echo "  Tune Engine  http://127.0.0.1:8100/docs"
echo "  check-mcp    http://127.0.0.1:8200/health"
echo "  run-log-mcp  http://127.0.0.1:8300/health"
echo ""
echo "他人接入见：docs/他人接入指南.md"
