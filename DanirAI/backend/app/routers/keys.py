"""Личные API-ключи: доступ к DanirAI из своих программ (как у OpenAI)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ApiKey, User
from ..security import hash_api_key, new_api_key

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


@router.get("")
def list_keys(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())).scalars().all()
    return [
        {
            "id": k.id, "name": k.name, "prefix": k.prefix,
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in rows
    ]


@router.post("", status_code=201)
def create_key(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.execute(select(ApiKey).where(ApiKey.user_id == user.id)).scalars().all()
    if len(existing) >= 5:
        raise HTTPException(status_code=400, detail="Максимум 5 ключей на аккаунт")
    raw = new_api_key()
    key = ApiKey(user_id=user.id, name=(payload.get("name") or "default")[:80], key_hash=hash_api_key(raw), prefix=raw[:12])
    db.add(key)
    db.commit()
    db.refresh(key)
    return {
        "id": key.id,
        "name": key.name,
        "api_key": raw,  # показывается ТОЛЬКО один раз
        "warning": "Сохраните ключ сейчас — повторно его увидеть нельзя.",
        "usage": "curl -H 'X-API-Key: %s' https://ваш-домен/api/chats" % raw,
    }


@router.delete("/{key_id}")
def delete_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="Ключ не найден")
    db.delete(key)
    db.commit()
    return {"ok": True}
