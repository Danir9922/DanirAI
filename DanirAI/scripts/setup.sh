#!/usr/bin/env bash
# DanirAI — установка зависимостей и первый запуск
set -e
cd "$(dirname "$0")/.."

echo " DanirAI setup"
python3 -m pip install --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install -r backend/requirements.txt
python3 -m pip install pillow imageio-ffmpeg

if [ ! -f .env ]; then
  cp .env.example .env
  echo "📄 Создан .env (заполните OPENAI_API_KEY, если хотите уровень ChatGPT)"
fi

echo
echo "✅ Готово! Запуск:  bash scripts/run.sh"
echo "   или:            cd backend && uvicorn app.main:app --port 8000"
