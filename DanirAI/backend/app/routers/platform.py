"""Публичный каталог моделей, тарифов и статус платформы."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import APP_NAME, APP_VERSION, MODEL_CATALOG, PLANS
from ..providers import provider_status

router = APIRouter(prefix="/api", tags=["platform"])


@router.get("/models")
def models():
    """Каталог моделей DanirAI (виден всем, даже без входа)."""
    return {"models": MODEL_CATALOG}


@router.get("/plans")
def plans():
    """Тарифные планы и цены."""
    return {"plans": PLANS, "currency": "KZT"}


@router.get("/status")
def status():
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "providers": provider_status(),
        "models": [m["id"] for m in MODEL_CATALOG],
        "ok": True,
    }


@router.get("/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}
