#!/usr/bin/env bash
# DanirAI — запуск сервера
set -e
cd "$(dirname "$0")/../backend"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "🚀 DanirAI стартует на http://localhost:${PORT}  (документация: /docs)"
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT"
