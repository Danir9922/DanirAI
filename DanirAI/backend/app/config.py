"""Глобальные настройки DanirAI.

Все значения читаются из переменных окружения (или файла .env),
поэтому проект одинаково работает и локально, и в облаке.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # .../DanirAI/backend
ROOT_DIR = BASE_DIR.parent                              # .../DanirAI
DATA_DIR = Path(os.getenv("DANIRAI_DATA_DIR", ROOT_DIR / "data"))
MEDIA_DIR = DATA_DIR / "media"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """Простой .env-загрузчик (без внешних зависимостей)."""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

APP_NAME = os.getenv("APP_NAME", "DanirAI")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ACCESS_TOKEN_TTL_MIN = int(os.getenv("ACCESS_TOKEN_TTL_MIN", 60 * 24 * 7))  # 7 дней

# --- База данных -----------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'danirai.db'}")

# --- Провайдеры моделей ----------------------------------------------------
# OPENAI_API_KEY — для DanirAI-1v / 1 PRO / Deep Research, если подключён.
# Если ключа нет — работает встроенный офлайн-провайдер (echo-brain),
# чтобы платформа жила и без внешних API.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Бесплатные публичные провайдеры (без ключей)
POLLINATIONS_TEXT_URL = os.getenv("POLLINATIONS_TEXT_URL", "https://text.pollinations.ai")
POLLINATIONS_IMAGE_URL = os.getenv("POLLINATIONS_IMAGE_URL", "https://image.pollinations.ai/prompt")
POLLINATIONS_VIDEO_URL = os.getenv("POLLINATIONS_VIDEO_URL", "https://text.pollinations.ai")

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "duckduckgo")  # duckduckgo | searxng | none
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888/search")

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", 60))

# --- Платежи ---------------------------------------------------------------
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "mock")    # mock | kassa | cloudpayments
PAYMENT_SECRET = os.getenv("PAYMENT_SECRET", "dev-payment-secret")

# --- Каталог моделей DanirAI ----------------------------------------------
# kind: chat | image | video | research
# tier: free | plus | pro
MODEL_CATALOG = [
    {
        "id": "danirai-1v",
        "name": "DanirAI-1v",
        "tagline": "Быстрая модель — мгновенные ответы",
        "kind": "chat",
        "tier": "free",
        "reasoning": False,
        "context": 32_000,
        "icon": "⚡",
        "description": "Первая модель DanirAI. Отвечает быстро и по делу, без долгого размышления.",
    },
    {
        "id": "danirai-1-pro",
        "name": "DanirAI-1 PRO",
        "tagline": "Глубоко думает перед ответом",
        "kind": "chat",
        "tier": "plus",
        "reasoning": True,
        "context": 128_000,
        "icon": "🧠",
        "description": "Модель с режимом мышления: сначала строит цепочку рассуждений, потом выдаёт ответ.",
    },
    {
        "id": "danirai-research",
        "name": "DanirAI Deep Research",
        "tagline": "Ищет в интернете и делает полный разбор",
        "kind": "research",
        "tier": "pro",
        "reasoning": True,
        "context": 128_000,
        "icon": "🔎",
        "description": "Агент глубокого исследования: сам ищет в интернете, читает страницы и собирает отчёт с источниками.",
    },
    {
        "id": "danirai-agent",
        "name": "DanirAI Agent",
        "tagline": "Автономный агент с инструментами",
        "kind": "research",
        "tier": "pro",
        "reasoning": True,
        "context": 128_000,
        "icon": "🤖",
        "description": "Агент, который сам решает задачу: ищет, читает, считает, рисует картинки и пишет код.",
    },
    {
        "id": "danirai-image",
        "name": "DanirAI Image",
        "tagline": "Генерация изображений",
        "kind": "image",
        "tier": "plus",
        "reasoning": False,
        "context": 0,
        "icon": "🎨",
        "description": "Рисует картинки по текстовому описанию.",
    },
    {
        "id": "danirai-video",
        "name": "DanirAI Video",
        "tagline": "Генерация видео",
        "kind": "video",
        "tier": "pro",
        "reasoning": False,
        "context": 0,
        "icon": "🎬",
        "description": "Создаёт короткие видеоролики по описанию сцены.",
    },
]

MODELS_BY_ID = {m["id"]: m for m in MODEL_CATALOG}

# --- Тарифные планы --------------------------------------------------------
PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price": 0,
        "price_label": "0 ₸",
        "period": "навсегда",
        "highlight": False,
        "messages_per_day": 50,
        "images_per_day": 3,
        "videos_per_day": 0,
        "research_per_day": 0,
        "models": ["danirai-1v", "danirai-image"],
        "features": [
            "DanirAI-1v — быстрые ответы",
            "50 сообщений в день",
            "3 картинки в день",
            "История чатов и профиль",
        ],
    },
    {
        "id": "plus",
        "name": "Plus",
        "price": 9990,
        "price_label": "9 990 ₸",
        "period": "в месяц",
        "highlight": True,
        "messages_per_day": 1000,
        "images_per_day": 200,
        "videos_per_day": 0,
        "research_per_day": 0,
        "models": ["danirai-1v", "danirai-1-pro", "danirai-image"],
        "features": [
            "DanirAI-1 PRO — глубокое мышление",
            "1000 сообщений в день",
            "200 картинок в день",
            "Приоритетная скорость ответов",
            "Бейдж Plus в профиле",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": 50000,
        "price_label": "50 000 ₸",
        "period": "в месяц",
        "highlight": False,
        "messages_per_day": -1,  # безлимит
        "images_per_day": -1,
        "videos_per_day": 20,
        "research_per_day": 30,
        "models": ["danirai-1v", "danirai-1-pro", "danirai-research", "danirai-agent", "danirai-image", "danirai-video"],
        "features": [
            "Все модели, включая Deep Research и Agent",
            "Безлимит сообщений и картинок",
            "Генерация видео — 20 в день",
            "Поиск в интернете с источниками",
            "Ранний доступ к новым моделям",
        ],
    },
]

PLANS_BY_ID = {p["id"]: p for p in PLANS}
TIER_RANK = {"free": 0, "plus": 1, "pro": 2}
