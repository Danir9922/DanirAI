"""DanirAI Video — генерация видео.

Пайплайн:
1. По промпту строится раскадровка (несколько ключевых кадров).
2. Каждый кадр рисуется генератором изображений (Pollinations FLUX / DALL·E).
3. Кадры анимируются (эффект Ken Burns + плавные переходы) и кодируются
   в настоящий MP4 через ffmpeg. Если ffmpeg недоступен — сохраняется GIF.
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import MEDIA_DIR

try:
    import imageio_ffmpeg  # type: ignore

    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # pragma: no cover
    FFMPEG = shutil.which("ffmpeg") or ""

W, H, FPS = 768, 768, 24


def video_enabled() -> bool:
    return True


def has_ffmpeg() -> bool:
    return bool(FFMPEG)


def _find_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def build_storyboard(prompt: str, duration: int = 5) -> list[str]:
    """Разбивает промпт на ключевые кадры."""
    parts = [p.strip() for p in prompt.replace(";", ",").split(",") if p.strip()]
    scenes = parts[:4] if len(parts) >= 2 else [prompt]
    while len(scenes) < 3:
        scenes.append(prompt)
    shots = ["wide establishing shot", "medium shot, cinematic lighting", "close-up detail", "dramatic final shot"]
    out = []
    for i, scene in enumerate(scenes[: max(3, min(6, duration))]):
        out.append(f"{scene}, {shots[i % len(shots)]}, high quality, cinematic, detailed, 4k")
    return out


async def fetch_frames(client: httpx.AsyncClient, scenes: list[str], image_fn) -> list[Path]:
    tmp = Path(MEDIA_DIR) / "frames" / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    async def one(i: int, scene: str) -> tuple[int, Path | None]:
        try:
            data = await image_fn(scene, width=W, height=H)
            if not data:
                return i, None
            p = tmp / f"frame_{i:02d}.png"
            p.write_bytes(data)
            return i, p
        except Exception:
            return i, None

    results = await asyncio.gather(*[one(i, s) for i, s in enumerate(scenes)])
    for i, p in sorted(results, key=lambda x: x[0]):
        if p:
            paths.append(p)

    if not paths:  # нет интернета → рисуем кадры сами
        for i, scene in enumerate(scenes):
            p = tmp / f"frame_{i:02d}.png"
            _placeholder_frame(p, scene, i)
            paths.append(p)
    return paths


def _placeholder_frame(path: Path, text: str, idx: int) -> None:
    hue = (idx * 47) % 360
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            t = (x / W + y / H) / 2
            r = int(60 + 140 * abs(math.sin(t * 3 + hue / 57)))
            g = int(40 + 120 * abs(math.cos(t * 2 + idx)))
            b = int(120 + 120 * abs(math.sin(t * 4 + hue / 90)))
            for dy in range(4):
                for dx in range(4):
                    if x + dx < W and y + dy < H:
                        px[x + dx, y + dy] = (r, g, b)
    img = img.filter(ImageFilter.GaussianBlur(2))
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, H - 120, W, H], fill=(0, 0, 0, 160))
    draw.text((24, H - 96), "DanirAI Video", font=_find_font(30), fill=(255, 255, 255, 255))
    draw.text((24, H - 56), text[:60], font=_find_font(20), fill=(200, 210, 255, 255))
    img.save(path)


def _ken_burns(img: Image.Image, t: float, mode: int) -> Image.Image:
    """Плавный зум/панорама: t ∈ [0,1]."""
    zoom = 1.0 + 0.16 * t if mode % 2 == 0 else 1.16 - 0.16 * t
    cw, ch = int(W / zoom), int(H / zoom)
    dx = int((img.width - cw) * (0.5 + 0.3 * math.sin(t * math.pi) * (1 if mode < 2 else -1)))
    dy = int((img.height - ch) * (0.5 + 0.2 * math.cos(t * math.pi)))
    dx = max(0, min(img.width - cw, dx))
    dy = max(0, min(img.height - ch, dy))
    return img.crop((dx, dy, dx + cw, dy + ch)).resize((W, H), Image.LANCZOS)


def _crossfade(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    return Image.blend(a, b, t)


def render_video(frames: list[Path], out_path: Path, *, duration: int = 5, title: str = "") -> Path:
    total = max(24, duration * FPS)
    per = max(1, total // len(frames))
    imgs = [Image.open(p).convert("RGB").resize((W, H)) for p in frames]

    out_gif = out_path.with_suffix(".gif")
    gif_frames: list[Image.Image] = []
    png_dir = out_path.parent / f"_{out_path.stem}_png"
    png_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for i, base in enumerate(imgs):
        nxt = imgs[(i + 1) % len(imgs)]
        for f in range(per):
            t = f / per
            cur = _ken_burns(base, t, i)
            if f >= per - 6:  # плавный переход к следующему кадру
                blend = (f - (per - 6)) / 6
                cur = _crossfade(cur, _ken_burns(nxt, 0, i + 1), blend)
            if n % 3 == 0:
                gif_frames.append(cur.resize((W // 2, H // 2)))
            cur.save(png_dir / f"f_{n:05d}.png")
            n += 1

    if title:
        _stamp_watermark(png_dir, n, title)

    if FFMPEG:
        cmd = [
            FFMPEG, "-y", "-framerate", str(FPS), "-i", str(png_dir / "f_%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-crf", "23", "-movflags", "+faststart", str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        shutil.rmtree(png_dir, ignore_errors=True)
        if proc.returncode == 0 and out_path.exists():
            return out_path

    # запасной вариант — анимированный GIF
    if gif_frames:
        gif_frames[0].save(out_gif, save_all=True, append_images=gif_frames[1:], duration=int(1000 / 8), loop=0, optimize=False)
    shutil.rmtree(png_dir, ignore_errors=True)
    return out_gif if out_gif.exists() else out_path


def _stamp_watermark(png_dir: Path, count: int, title: str) -> None:
    font = _find_font(26)
    for p in sorted(png_dir.glob("f_*.png"))[:count]:
        try:
            im = Image.open(p).convert("RGBA")
            draw = ImageDraw.Draw(im, "RGBA")
            draw.text((20, H - 44), f"DanirAI • {title[:38]}", font=font, fill=(255, 255, 255, 220))
            im.convert("RGB").save(p)
        except Exception:
            continue


async def generate_video(prompt: str, image_fn, *, duration: int = 5, out_dir: Path | None = None) -> dict:
    """Главная функция: промпт → файл видео."""
    duration = max(2, min(15, duration))
    scenes = build_storyboard(prompt, duration)
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        frames = await fetch_frames(client, scenes, image_fn)
    out_dir = out_dir or Path(MEDIA_DIR) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    vid = uuid.uuid4().hex
    ext = ".mp4" if FFMPEG else ".gif"
    out_path = out_dir / f"{vid}{ext}"
    result = await asyncio.to_thread(render_video, frames, out_path, duration=duration, title=prompt[:38])
    for f in frames:
        try:
            f.unlink()
        except Exception:
            pass
    return {
        "path": str(result),
        "name": result.name,
        "format": result.suffix.lstrip("."),
        "duration": duration,
        "scenes": scenes,
        "engine": "ffmpeg" if result.suffix == ".mp4" else "gif-fallback",
        "seed": random.randint(1, 10**9),
    }
