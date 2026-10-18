"""Выбор провайдера: OpenAI (если есть ключ) → Pollinations → Local Brain."""
from __future__ import annotations

from ..config import OPENAI_API_KEY
from .base import BaseProvider, GenResult
from .local_brain import LocalBrainProvider
from .openai_provider import OpenAIProvider
from .pollinations import PollinationsProvider

_openai = OpenAIProvider() if OPENAI_API_KEY else None
_pollinations = PollinationsProvider()
_local = LocalBrainProvider()

CHAIN: list[BaseProvider] = [p for p in (_openai, _pollinations, _local) if p is not None]


def active_chain() -> list[BaseProvider]:
    return CHAIN


def openai_provider() -> OpenAIProvider | None:
    """OpenAI-провайдер, если подключён ключ."""
    return _openai


def pollinations_provider() -> PollinationsProvider:
    return _pollinations


def provider_status() -> dict:
    return {
        "openai": bool(_openai),
        "pollinations": True,
        "local": True,
        "active": CHAIN[0].name if CHAIN else "none",
    }


async def smart_chat(messages, **kwargs) -> GenResult:
    """Пробует провайдеров по очереди: если один упал — берёт следующий."""
    last_error: Exception | None = None
    for provider in CHAIN:
        try:
            result = await provider.chat(messages, **kwargs)
            if result.text.strip():
                return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if last_error:
        raise last_error
    return GenResult(text="DanirAI не смог ответить. Попробуйте ещё раз.", provider="none")
