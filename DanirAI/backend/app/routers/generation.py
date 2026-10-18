"""Генерация: картинки, видео, озвучка."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import MEDIA_DIR, MODELS_BY_ID
from ..database import get_db
from ..deps import bump_usage, check_quota, get_current_user, plan_of
from ..models import Asset, Chat, Message, User
from ..providers.video import FFMPEG, generate_video
from ..schemas import ImageGenIn, VideoGenIn
from ..services.image_service import generate_image
from ._util import message_to_dict

router = APIRouter(prefix="/api", tags=["generation"])

VIDEO_DIR = Path(MEDIA_DIR) / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# in-memory очередь задач на видео
JOBS: dict[str, dict[str, Any]] = {}
MAX_JOBS = 400


def _save_job(job_id: str, data: dict) -> None:
    if len(JOBS) > MAX_JOBS:
        for k in sorted(JOBS, key=lambda x: JOBS[x].get("created", ""))[: len(JOBS) - MAX_JOBS]:
            JOBS.pop(k, None)
    JOBS[job_id] = {"id": job_id, "created": datetime.now(timezone.utc).isoformat(), **data}


async def _image_bytes_fn(prompt: str, *, width: int = 768, height: int = 768) -> bytes | None:
    """Функция получения кадров для видео: пробуем скачать настоящую картинку."""
    import httpx

    from ..providers import openai_provider
    from ..providers.pollinations import PollinationsProvider

    provider = openai_provider()
    if provider is not None:
        try:
            data = await provider.image(prompt, width=1024, height=1024)
            if data.get("url"):
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
                    r = await c.get(data["url"])
                    if r.status_code == 200:
                        return r.content
        except Exception:
            pass
    try:
        return await PollinationsProvider().image_bytes(prompt, width=width, height=height)
    except Exception:
        return None


# --- Картинки --------------------------------------------------------------
@router.post("/images")
async def create_image(payload: ImageGenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _check_model_access(user, payload.model_id, "image")
    check_quota(db, user, "image", "images_per_day")

    result = await generate_image(payload.prompt, width=payload.width, height=payload.height)
    asset = Asset(
        user_id=user.id,
        chat_id=payload.chat_id,
        kind="image",
        prompt=payload.prompt,
        model_id=payload.model_id,
        url=result["url"],
    )
    db.add(asset)
    bump_usage(db, user.id, "image")

    if payload.chat_id:
        chat = db.get(Chat, payload.chat_id)
        if chat and chat.user_id == user.id:
            msg = Message(
                chat_id=chat.id,
                role="assistant",
                content=f"🎨 Картинка по запросу: *{payload.prompt}*",
                model_id=payload.model_id,
                attachments=json.dumps([{"kind": "image", "url": result["url"], "prompt": payload.prompt}], ensure_ascii=False),
            )
            db.add(msg)
            chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(asset)
    return {
        "asset": {"id": asset.id, "kind": "image", "url": asset.url, "prompt": asset.prompt},
        "generation": result,
        "usage": _usage(db, user),
    }


@router.get("/images")
def list_images(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.execute(
            select(Asset).where(Asset.user_id == user.id, Asset.kind == "image").order_by(Asset.created_at.desc()).limit(200)
        )
        .scalars()
        .all()
    )
    return [
        {"id": r.id, "url": r.url, "prompt": r.prompt, "model_id": r.model_id, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


# --- Видео -----------------------------------------------------------------
@router.post("/videos")
async def create_video(
    payload: VideoGenIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_model_access(user, payload.model_id, "video")
    check_quota(db, user, "video", "videos_per_day")

    job_id = uuid.uuid4().hex
    _save_job(job_id, {"status": "queued", "progress": 0, "prompt": payload.prompt, "user_id": user.id,
                       "duration": payload.duration, "stage": "Постановка в очередь"})
    bump_usage(db, user.id, "video")
    background.add_task(_video_job, job_id, payload.prompt, payload.duration, user.id, payload.chat_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "engine": "ffmpeg (MP4)" if FFMPEG else "GIF fallback",
        "message": "Генерация видео запущена. Обновляйте статус через GET /api/videos/jobs/{job_id}",
    }


async def _video_job(job_id: str, prompt: str, duration: int, user_id: str, chat_id: str | None) -> None:
    try:
        _save_job(job_id, {**JOBS[job_id], "status": "running", "progress": 15, "stage": "Раскадровка сцены"})

        from ..providers.video import build_storyboard

        scenes = build_storyboard(prompt, duration)
        _save_job(job_id, {**JOBS[job_id], "progress": 30, "stage": f"Рисую {len(scenes)} кадров нейросетью"})

        result = await generate_video(prompt, _image_bytes_fn, duration=duration, out_dir=VIDEO_DIR)

        rel_url = f"/media/videos/{result['name']}"
        _save_job(job_id, {**JOBS[job_id], "status": "done", "progress": 100, "stage": "Готово",
                           "url": rel_url, "format": result["format"], "scenes": result["scenes"],
                           "engine": result["engine"]})

        from ..database import SessionLocal

        db = SessionLocal()
        try:
            db.add(Asset(user_id=user_id, chat_id=chat_id, kind="video", prompt=prompt, model_id="danirai-video", url=rel_url))
            if chat_id:
                chat = db.get(Chat, chat_id)
                if chat and chat.user_id == user_id:
                    db.add(Message(
                        chat_id=chat.id, role="assistant",
                        content=f"🎬 Видео готово: *{prompt}*", model_id="danirai-video",
                        attachments=json.dumps([{"kind": "video", "url": rel_url}], ensure_ascii=False),
                    ))
                    chat.updated_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        _save_job(job_id, {**JOBS.get(job_id, {}), "status": "failed", "stage": f"Ошибка: {exc}", "error": str(exc)})


@router.get("/videos/jobs/{job_id}")
def video_job_status(job_id: str, user: User = Depends(get_current_user)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена (или сервер перезапустился)")
    if job.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")
    public = {k: v for k, v in job.items() if k != "user_id"}
    return public


@router.get("/videos")
def list_videos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.execute(
            select(Asset).where(Asset.user_id == user.id, Asset.kind == "video").order_by(Asset.created_at.desc()).limit(100)
        )
        .scalars()
        .all()
    )
    return [
        {"id": r.id, "url": r.url, "prompt": r.prompt, "model_id": r.model_id, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/videos/jobs")
def my_jobs(user: User = Depends(get_current_user)):
    return [
        {k: v for k, v in j.items() if k != "user_id"}
        for j in sorted(JOBS.values(), key=lambda x: x.get("created", ""), reverse=True)
        if j.get("user_id") == user.id
    ]


# --- Озвучка текста --------------------------------------------------------
@router.post("/speech")
async def text_to_speech(payload: dict, user: User = Depends(get_current_user)):
    """Простая озвучка: возвращает текст для синтеза на клиенте + ssml-подсказки."""
    text = (payload.get("text") or "").strip()[:2000]
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст")
    return {
        "text": text,
        "voice": payload.get("voice", "ru-RU"),
        "hint": "Воспроизведение через Web Speech API на клиенте (см. frontend/js/app.js)",
    }


# --- helpers ---------------------------------------------------------------
def _check_model_access(user: User, model_id: str, kind: str) -> dict:
    model = MODELS_BY_ID.get(model_id)
    if not model:
        raise HTTPException(status_code=400, detail=f"Неизвестная модель: {model_id}")
    if model["kind"] != kind:
        raise HTTPException(status_code=400, detail=f"{model_id} не является моделью типа {kind}")
    if model_id not in plan_of(user).get("models", []):
        raise HTTPException(status_code=402, detail=f"{model['name']} доступна на тарифе выше")
    return model


def _usage(db: Session, user: User) -> dict:
    from ..deps import usage_count

    return {
        "messages": usage_count(db, user.id, "message"),
        "images": usage_count(db, user.id, "image"),
        "videos": usage_count(db, user.id, "video"),
        "research": usage_count(db, user.id, "research"),
        "plan": plan_of(user),
    }
