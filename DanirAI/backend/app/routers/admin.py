"""Админ-панель: статистика, пользователи, управление тарифами."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_admin_user, get_current_user, plan_of, usage_count
from ..models import Asset, Chat, Message, Payment, User
from ..providers import provider_status

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    total_users = db.execute(select(func.count()).select_from(User)).scalar_one()
    total_chats = db.execute(select(func.count()).select_from(Chat)).scalar_one()
    total_messages = db.execute(select(func.count()).select_from(Message)).scalar_one()
    paid = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid")
    ).scalar_one()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_users = db.execute(
        select(func.count(func.distinct(Chat.user_id))).where(Chat.updated_at >= week_ago)
    ).scalar_one()
    by_tier = {
        row[0]: row[1] for row in db.execute(select(User.tier, func.count()).group_by(User.tier)).all()
    }
    assets = db.execute(select(func.count()).select_from(Asset)).scalar_one()
    return {
        "users": {"total": total_users, "active_7d": active_users, "by_tier": by_tier},
        "chats": total_chats,
        "messages": total_messages,
        "assets": assets,
        "revenue_kzt": paid,
        "providers": provider_status(),
    }


@router.get("/users")
def users(db: Session = Depends(get_db), admin: User = Depends(get_admin_user), limit: int = 100):
    rows = db.execute(select(User).order_by(User.created_at.desc()).limit(min(limit, 500))).scalars().all()
    return [
        {
            "id": u.id, "email": u.email, "display_name": u.display_name, "tier": u.tier,
            "is_admin": u.is_admin, "avatar_url": u.avatar_url,
            "created_at": u.created_at.isoformat(),
            "chats": db.execute(select(func.count()).select_from(Chat).where(Chat.user_id == u.id)).scalar_one(),
            "messages_today": usage_count(db, u.id, "message"),
        }
        for u in rows
    ]


@router.patch("/users/{user_id}")
def set_user_tier(user_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    tier = payload.get("tier")
    if tier not in {"free", "plus", "pro"}:
        raise HTTPException(status_code=400, detail="tier должен быть free | plus | pro")
    user.tier = tier
    if tier == "free":
        user.tier_expires_at = None
    else:
        user.tier_expires_at = datetime.now(timezone.utc) + timedelta(days=int(payload.get("days", 30)))
    if "is_admin" in payload:
        user.is_admin = bool(payload["is_admin"])
    db.commit()
    return {"id": user.id, "tier": user.tier, "expires_at": user.tier_expires_at.isoformat() if user.tier_expires_at else None}


@router.get("/payments")
def payments(db: Session = Depends(get_db), admin: User = Depends(get_admin_user), limit: int = 100):
    rows = db.execute(select(Payment).order_by(Payment.created_at.desc()).limit(limit)).scalars().all()
    out = []
    for p in rows:
        u = db.get(User, p.user_id)
        out.append({
            "id": p.id, "user": u.email if u else "?", "plan_id": p.plan_id, "amount": p.amount,
            "status": p.status, "provider": p.provider, "created_at": p.created_at.isoformat(),
        })
    return out
