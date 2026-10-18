"""Генерация картинок: скачиваем результат и храним у себя в /media."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import httpx

from ..config import MEDIA_DIR, OPENAI_API_KEY
from ..providers import openai_provider
from ..providers.pollinations import PollinationsProvider

_openai = openai_provider()
_poll = PollinationsProvider()
IMAGES_DIR = Path(MEDIA_DIR) / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


async def generate_image(prompt: str, *, width: int = 1024, height: int = 1024) -> dict:
    """Возвращает {'file': имя файла, 'url': /media/images/..., 'prompt':...}."""
    width = max(256, min(1536, width))
    height = max(256, min(1536, height))

    if _openai is not None and OPENAI_API_KEY:
        try:
            data = await _openai.image(prompt, width=1024, height=1024)
            if data.get("url"):
                saved = await _download(data["url"])
                if saved:
                    return saved
        except Exception:
            pass  # падаем на бесплатный провайдер

    info = await _poll.image(prompt, width=width, height=height)
    try:
        raw = await _poll.image_bytes(prompt, width=width, height=height)
        name = f"{uuid.uuid4().hex}.jpg"
        (IMAGES_DIR / name).write_bytes(raw)
        return {
            "file": name,
            "url": f"/media/images/{name}",
            "prompt": prompt,
            "width": width,
            "height": height,
            "provider": "pollinations",
            "seed": info.get("seed"),
            "size_kb": round(len(raw) / 1024, 1),
        }
    except Exception:
        # интернет недоступен → рисуем картинку сами (локальный арт)
        return _local_art(prompt, width, height)


async def _download(url: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
            name = f"{uuid.uuid4().hex}{ext}"
            (IMAGES_DIR / name).write_bytes(r.content)
            return {
                "file": name,
                "url": f"/media/images/{name}",
                "width": 1024,
                "height": 1024,
                "provider": "openai",
                "size_kb": round(len(r.content) / 1024, 1),
            }
    except Exception:
        return None


def _local_art(prompt: str, width: int, height: int) -> dict:
    """Офлайн-генератор абстрактного арта (когда нет интернета)."""
    from PIL import Image, ImageDraw, ImageFilter

    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    img = Image.new("RGB", (width, height), (12, 14, 28))
    draw = ImageDraw.Draw(img, "RGBA")
    rnd = seed
    for i in range(60):
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        x = rnd % width
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        y = rnd % height
        r = 20 + rnd % 140
        color = ((seed + i * 37) % 255, (seed * 3 + i * 61) % 255, (seed * 7 + i * 97) % 255, 70)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    img = img.filter(ImageFilter.GaussianBlur(28))
    d2 = ImageDraw.Draw(img, "RGBA")
    d2.rectangle([0, height - 70, width, height], fill=(0, 0, 0, 150))
    d2.text((18, height - 52), f"DanirAI Image (offline) • {prompt[:52]}", fill=(255, 255, 255, 230))
    name = f"{uuid.uuid4().hex}.png"
    img.save(IMAGES_DIR / name)
    return {
        "file": name,
        "url": f"/media/images/{name}",
        "prompt": prompt,
        "width": width,
        "height": height,
        "provider": "local-art",
    }
