"""Регистрация, вход, профиль, аватар."""
from __future__ import annotations

import io
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import APP_NAME, MEDIA_DIR
from ..database import get_db
from ..deps import get_current_user, plan_of
from ..models import User
from ..schemas import LoginIn, ProfileUpdate, RegisterIn, TokenOut, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

AVATAR_DIR = MEDIA_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name or user.email.split("@")[0],
        "avatar_url": user.avatar_url,
        "bio": user.bio or "",
        "tier": user.tier,
        "tier_expires_at": user.tier_expires_at.isoformat() if user.tier_expires_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "plan": plan_of(user),
    }


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Этот email уже зарегистрирован. Войдите в аккаунт.")

    is_first = (db.execute(select(func.count()).select_from(User)).scalar_one() or 0) == 0
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip() or email.split("@")[0],
        is_admin=is_first,  # первый зарегистрировавшийся — админ
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    response.set_cookie("danirai_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return TokenOut(access_token=token, user=UserOut.model_validate(_user_out(user)))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_token(user.id)
    response.set_cookie("danirai_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return TokenOut(access_token=token, user=UserOut.model_validate(_user_out(user)))


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("danirai_token")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.patch("/me")
def update_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()[:80]
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip()[:500]
    if payload.bio is not None:
        user.bio = payload.bio.strip()[:500]
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Загрузка аватара профиля (jpg/png/webp/gif, до 5 МБ)."""
    if file.content_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise HTTPException(status_code=400, detail="Можно загружать только картинки PNG/JPEG/WebP/GIF")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 5 МБ")

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        size = min(img.size)
        left = (img.width - size) // 2
        top = (img.height - size) // 2
        img = img.crop((left, top, left + size, top + size)).resize((256, 256), Image.LANCZOS)
        name = f"{uuid.uuid4().hex}.jpg"
        img.save(AVATAR_DIR / name, quality=90)
    except Exception:
        ext = (file.filename or "a.png").rsplit(".", 1)[-1].lower()[:4] or "png"
        if not re.fullmatch(r"(png|jpg|jpeg|webp|gif)", ext):
            ext = "png"
        name = f"{uuid.uuid4().hex}.{ext}"
        (AVATAR_DIR / name).write_bytes(raw)

    user.avatar_url = f"/media/avatars/{name}"
    db.commit()
    return {"avatar_url": user.avatar_url}


@router.post("/me/avatar/generate")
async def generate_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Сгенерировать аватар нейросетью по описанию пользователя."""
    from ..services.image_service import generate_image

    prompt = (
        f"minimalist modern avatar icon for a user named {user.display_name or 'Danir'}, "
        "abstract geometric portrait, vibrant gradient background, flat vector style, centered"
    )
    result = await generate_image(prompt, width=512, height=512)
    user.avatar_url = result["url"]
    db.commit()
    return {"avatar_url": user.avatar_url, "generation": result}
