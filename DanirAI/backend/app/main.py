"""DanirAI — точка входа FastAPI-приложения."""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, DATA_DIR, MODELS_BY_ID, MODEL_CATALOG, ROOT_DIR
from .database import init_db
from .routers import admin, auth, billing, chat, generation, keys, platform, research

FRONTEND_DIR = ROOT_DIR / "frontend"
MEDIA_DIR = DATA_DIR / "media"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .providers import provider_status

    print(f"\n  🚀 {APP_NAME} v{APP_VERSION} запущен")
    print(f"  📦 Провайдеры: {provider_status()}")
    print(f"  🗄  База: {DATA_DIR / 'danirai.db'}\n")
    yield


app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description=(
        "DanirAI — платформа искусственного интеллекта: чаты, модели (DanirAI-1v, DanirAI-1 PRO), "
        "Deep Research, генерация изображений и видео, профили, тарифы и API-ключи."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start) * 1000:.1f}ms"
    response.headers["X-DanirAI-Version"] = APP_VERSION
    return response


# --- API-роутеры -----------------------------------------------------------
app.include_router(platform.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chat.share_router)
app.include_router(generation.router)
app.include_router(research.router)
app.include_router(billing.router)
app.include_router(keys.router)
app.include_router(admin.router)


# --- OpenAI-совместимый API (чтобы к DanirAI подключались любые клиенты) ----
@app.post("/v1/chat/completions")
async def openai_compatible_chat(request: Request):
    from .deps import get_db
    from .models import ApiKey, User
    from .providers import smart_chat
    from .security import hash_api_key

    body = await request.json()
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-api-key", "")
    if not token:
        return JSONResponse({"error": {"message": "Нужен API-ключ DanirAI", "type": "invalid_request_error"}}, status_code=401)

    db = next(get_db())
    try:
        row = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(token)).first()
        if not row:
            return JSONResponse({"error": {"message": "Неверный API-ключ", "type": "invalid_api_key"}}, status_code=401)
        user = db.get(User, row.user_id)
        requested = body.get("model", "danirai-1v")
        model_id = requested if requested in MODELS_BY_ID else "danirai-1v"
        messages = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in body.get("messages", [])
            if isinstance(m.get("content"), str)
        ]
        model = MODELS_BY_ID[model_id]
        result = await smart_chat(
            messages,
            model_id=model_id,
            reasoning=bool(model.get("reasoning")),
            temperature=float(body.get("temperature", 0.7)),
            max_tokens=int(body.get("max_tokens", 1500)),
        )
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": result.text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": result.tokens, "total_tokens": result.tokens},
        }
    finally:
        db.close()


@app.get("/v1/models")
async def openai_compatible_models():
    return {
        "object": "list",
        "data": [
            {"id": m["id"], "object": "model", "owned_by": "DanirAI", "name": m["name"]}
            for m in MODEL_CATALOG
        ],
    }


# --- Статика и фронтенд ----------------------------------------------------
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/api", include_in_schema=False)
def api_index():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "endpoints": [
            "/api/models", "/api/plans", "/api/status",
            "/api/auth/register", "/api/auth/login", "/api/auth/me",
            "/api/chats", "/api/chats/{id}/messages", "/api/chats/{id}/messages/stream",
            "/api/images", "/api/videos", "/api/videos/jobs/{id}",
            "/api/research", "/api/search", "/api/read",
            "/api/billing/plans", "/api/billing/checkout",
            "/api/keys", "/api/admin/stats",
            "/v1/chat/completions", "/v1/models",
        ],
        "models": [m["id"] for m in MODEL_CATALOG],
    }


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """Отдаём фронтенд (SPA) для всех не-API адресов."""
    if full_path.startswith(("api/", "v1/", "media/", "docs", "redoc", "openapi.json")):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    candidate = FRONTEND_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"detail": f"{APP_NAME} API. Откройте /docs для документации."})
