"""Pollinations.ai — бесплатный провайдер без ключей.

Даёт DanirAI настоящие ответы нейросети, генерацию картинок и «видео»
(покадровая анимация), даже когда не подключены платные API.
"""
from __future__ import annotations

import hashlib
import random
import urllib.parse
from typing import Any

import httpx

from ..config import POLLINATIONS_IMAGE_URL, POLLINATIONS_TEXT_URL, REQUEST_TIMEOUT
from .base import BaseProvider, GenResult
from .openai_provider import REASONING_PERSONA, SYSTEM_PERSONA


class PollinationsProvider(BaseProvider):
    name = "pollinations"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, read=180.0), follow_redirects=True)

    # --- Текст -------------------------------------------------------------
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
            persona = f"{persona}\n\n{system}"

        payload = {
            "messages": [{"role": "system", "content": persona}, *messages][-24:],
            "model": "openai",
            "seed": random.randint(1, 10**9),
            "temperature": temperature,
            "private": True,
            "referrer": "DanirAI",
        }
        try:
            r = await self.client.post(POLLINATIONS_TEXT_URL, json=payload)
            r.raise_for_status()
            text = (r.text or "").strip()
        except Exception:
            # запасной GET-запрос
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            url = f"{POLLINATIONS_TEXT_URL}/{urllib.parse.quote(last_user[:1800])}?model=openai&system={urllib.parse.quote(persona[:1500])}"
            r = await self.client.get(url)
            r.raise_for_status()
            text = (r.text or "").strip()

        reasoning_text = ""
        if "<thinking>" in text and "</thinking>" in text:
            reasoning_text = text.split("<thinking>", 1)[1].split("</thinking>", 1)[0].strip()
            text = text.split("</thinking>", 1)[1].strip()

        if not text:
            raise RuntimeError("Пустой ответ провайдера")

        return GenResult(
            text=text,
            reasoning=reasoning_text,
            tokens=len(text) // 4,
            provider=self.name,
        )

    # --- Картинки ----------------------------------------------------------
    async def image(self, prompt: str, *, width: int = 1024, height: int = 1024) -> dict[str, Any]:
        seed = int(hashlib.md5((prompt + str(random.random())).encode()).hexdigest()[:8], 16)
        url = (
            f"{POLLINATIONS_IMAGE_URL}/{urllib.parse.quote(prompt[:900])}"
            f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux&referrer=DanirAI"
        )
        return {"url": url, "revised_prompt": prompt, "seed": seed}

    async def image_bytes(self, prompt: str, *, width: int = 1024, height: int = 1024, seed: int | None = None) -> bytes:
        seed = seed if seed is not None else random.randint(1, 10**9)
        url = (
            f"{POLLINATIONS_IMAGE_URL}/{urllib.parse.quote(prompt[:900])}"
            f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux&referrer=DanirAI"
        )
        r = await self.client.get(url)
        r.raise_for_status()
        return r.content
