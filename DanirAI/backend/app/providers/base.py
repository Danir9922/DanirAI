"""Базовый интерфейс провайдера моделей DanirAI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class GenResult:
    text: str = ""
    reasoning: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    provider: str = ""


class BaseProvider:
    name = "base"

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model_id: str,
        system: str = "",
        reasoning: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
    ) -> GenResult:
        raise NotImplementedError

    def stream(self, *args, **kwargs) -> AsyncIterator[str]:
        raise NotImplementedError

    async def image(self, prompt: str, *, width: int = 1024, height: int = 1024) -> dict[str, Any]:
        raise NotImplementedError

    async def video(self, prompt: str, *, duration: int = 5) -> dict[str, Any]:
        raise NotImplementedError
