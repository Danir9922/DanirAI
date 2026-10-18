"""Зависимости FastAPI: текущий пользователь, БД, права по тарифу."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PLANS_BY_ID, TIER_RANK
from .database import get_db
from .models import ApiKey, UsageLog, User
from .security import decode_token, hash_api_key


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get("danirai_token", "")
    payload = decode_token(token) if token else None
    user: User | None = None

    if payload and payload.get("sub"):
        user = db.get(User, payload["sub"])
    else:
        # доступ по API-ключу (для внешних программ)
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            row = db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key))).scalar_one_or_none()
            if row:
                row.last_used_at = datetime.now(timezone.utc)
                db.commit()
                user = db.get(User, row.user_id)

    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт DanirAI")
    _refresh_tier(user, db)
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Только для администраторов")
    return user


def _refresh_tier(user: User, db: Session) -> None:
    """Если подписка истекла — возвращаем на Free."""
    if user.tier != "free" and user.tier_expires_at:
        exp = user.tier_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            user.tier = "free"
            user.tier_expires_at = None
            db.commit()


def plan_of(user: User) -> dict:
    return PLANS_BY_ID.get(user.tier, PLANS_BY_ID["free"])


def ensure_tier(user: User, required: str) -> None:
    """Проверяет, что тариф пользователя >= required."""
    if TIER_RANK.get(user.tier, 0) < TIER_RANK.get(required, 0):
        need = PLANS_BY_ID[required]["name"]
        raise HTTPException(
            status_code=402,
            detail=f"Эта функция доступна на тарифе {need}. Перейдите на вкладку «Тарифы».",
        )


def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def usage_count(db: Session, user_id: str, kind: str) -> int:
    row = db.execute(
        select(UsageLog).where(
            UsageLog.user_id == user_id, UsageLog.day == today_str(), UsageLog.kind == kind
        )
    ).scalar_one_or_none()
    return row.count if row else 0


def bump_usage(db: Session, user_id: str, kind: str, amount: int = 1) -> None:
    row = db.execute(
        select(UsageLog).where(
            UsageLog.user_id == user_id, UsageLog.day == today_str(), UsageLog.kind == kind
        )
    ).scalar_one_or_none()
    if row:
        row.count += amount
    else:
        db.add(UsageLog(user_id=user_id, day=today_str(), kind=kind, count=amount))
    db.commit()


def check_quota(db: Session, user: User, kind: str, field: str) -> None:
    """Проверяет дневной лимит. -1 означает безлимит."""
    limit = plan_of(user).get(field, 0)
    if limit == -1:
        return
    if limit == 0:
        need = "Pro" if field.endswith(("videos_per_day", "research_per_day")) else "Plus"
        raise HTTPException(status_code=402, detail=f"Лимит исчерпан: {field} недоступен на тарифе Free. Нужен {need}.")
    used = usage_count(db, user.id, kind)
    if used >= limit:
        raise HTTPException(status_code=429, detail=f"Дневной лимит {limit} исчерпан. Обновится завтра (UTC) или перейдите на тариф выше.")


def extend_subscription(db: Session, user: User, plan_id: str) -> User:
    base = datetime.now(timezone.utc)
    if user.tier_expires_at:
        exp = user.tier_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        base = max(base, exp)
    user.tier = plan_id
    user.tier_expires_at = base + timedelta(days=30)
    db.commit()
    return user
