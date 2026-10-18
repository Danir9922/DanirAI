"""Провайдер OpenAI (и любых OpenAI-совместимых API).

Включается, если задан OPENAI_API_KEY. Даёт DanirAI настоящие нейросетевые
ответы, генерацию картинок и режим мышления (reasoning) для DanirAI-1 PRO.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import OPENAI_API_KEY, OPENAI_BASE_URL, REQUEST_TIMEOUT
from .base import BaseProvider, GenResult

# Соответствие моделей DanirAI → базовым моделям провайдера.
# Можно переопределить через переменные окружения DANIRAI_MAP_*.
DEFAULT_MAP = {
    "danirai-1v": "gpt-4o-mini",
    "danirai-1-pro": "gpt-4o",
    "danirai-research": "gpt-4o",
    "danirai-agent": "gpt-4o",
    "danirai-image": "dall-e-3",
    "danirai-video": "",
}

SYSTEM_PERSONA = (
    "Ты — DanirAI, продвинутый искусственный интеллект-ассистент. "
    "Ты дружелюбный, умный и точный. Отвечай на языке пользователя. "
    "Используй markdown: заголовки, списки, таблицы и блоки кода, когда это уместно. "
    "Если не уверен — честно скажи об этом."
)

REASONING_PERSONA = (
    "Ты — DanirAI-1 PRO, модель с глубоким мышлением. Сначала проанализируй вопрос пошагово "
    "внутри <thinking>...</thinking>, а затем дай финальный ответ после тегов. "
    "Ответ должен быть подробным, структурированным и на языке пользователя."
)


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, api_key: str = OPENAI_API_KEY, base_url: str = OPENAI_BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _model(self, model_id: str) -> str:
        return DEFAULT_MAP.get(model_id, model_id)

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
        persona = REASONING_PERSONA if reasoning else SYSTEM_PERSONA
        if system:
            persona = f"{persona}\n\nДополнительные указания:\n{system}"
        payload: dict[str, Any] = {
            "model": self._model(model_id),
            "messages": [{"role": "system", "content": persona}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        r = await self.client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        raw = choice["message"].get("content") or ""
        tool_calls = choice["message"].get("tool_calls")

        reasoning_text = ""
        if reasoning and "<thinking>" in raw and "</thinking>" in raw:
            reasoning_text = raw.split("<thinking>", 1)[1].split("</thinking>", 1)[0].strip()
            raw = raw.split("</thinking>", 1)[1].strip()

        result = GenResult(
            text=raw,
            reasoning=reasoning_text,
            tokens=data.get("usage", {}).get("total_tokens", 0),
            provider=self.name,
        )
        if tool_calls:
            result.attachments = [{"type": "tool_calls", "data": tool_calls}]
        return result

    async def image(self, prompt: str, *, width: int = 1024, height: int = 1024) -> dict[str, Any]:
        payload = {
            "model": self._model("danirai-image") or "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "url",
        }
        r = await self.client.post(f"{self.base_url}/images/generations", json=payload, headers=self._headers())
        r.raise_for_status()
        item = r.json()["data"][0]
        return {"url": item.get("url", ""), "revised_prompt": item.get("revised_prompt", prompt)}

    async def video(self, prompt: str, *, duration: int = 5) -> dict[str, Any]:
        # Видео через OpenAI доступно не во всех аккаунтах — пробуем Sora-эндпоинт,
        # иначе падаем на fallback-провайдер (обрабатывается вызывающим кодом).
        payload = {"model": "sora-2", "prompt": prompt, "seconds": str(duration), "size": "720x1280"}
        r = await self.client.post(f"{self.base_url}/videos", json=payload, headers=self._headers())
        r.raise_for_status()
        data = r.json()
        video_id = data.get("id", "")
        return {"url": f"{self.base_url}/videos/{video_id}/content", "id": video_id}
