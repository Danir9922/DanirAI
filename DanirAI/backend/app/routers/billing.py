"""Оплата тарифов (Free / Plus / Pro), платёжные сессии и вебхуки."""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PAYMENT_PROVIDER, PAYMENT_SECRET, PLANS, PLANS_BY_ID
from ..database import get_db
from ..deps import extend_subscription, get_current_user, plan_of, usage_count
from ..models import Payment, User
from ..schemas import CheckoutIn, WebhookIn

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _sign(payment_id: str, amount: int, status: str) -> str:
    msg = f"{payment_id}:{amount}:{status}:{PAYMENT_SECRET}"
    return hmac.new(PAYMENT_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


@router.get("/plans")
def get_plans(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Тарифы + текущий статус пользователя и его лимиты."""
    return {
        "plans": PLANS,
        "currency": "KZT",
        "current": {
            "tier": user.tier,
            "plan": plan_of(user),
            "expires_at": user.tier_expires_at.isoformat() if user.tier_expires_at else None,
        },
        "usage_today": {
            "messages": usage_count(db, user.id, "message"),
            "images": usage_count(db, user.id, "image"),
            "videos": usage_count(db, user.id, "video"),
            "research": usage_count(db, user.id, "research"),
        },
    }


@router.post("/checkout")
def checkout(payload: CheckoutIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = PLANS_BY_ID.get(payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Такого тарифа нет")
    if plan["price"] == 0:
        raise HTTPException(status_code=400, detail="Free-тариф не требует оплаты")

    payment = Payment(
        user_id=user.id,
        plan_id=plan["id"],
        amount=plan["price"],
        currency="KZT",
        provider=PAYMENT_PROVIDER,
        external_id=f"ext_{uuid.uuid4().hex[:12]}",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    if PAYMENT_PROVIDER == "mock":
        # Демо-режим: платёж можно подтвердить сразу (в бою здесь будет ссылка на Kaspi/CloudPayments)
        return {
            "payment_id": payment.id,
            "provider": "mock",
            "amount": payment.amount,
            "currency": "KZT",
            "plan": plan["name"],
            "confirm_url": f"/api/billing/mock-confirm?payment_id={payment.id}&signature={_sign(payment.id, payment.amount, 'paid')}",
            "note": "Это тестовый режим оплаты. Подключите реальный провайдер через PAYMENT_PROVIDER и PAYMENT_SECRET.",
        }

    # Реальный провайдер: формируем ссылку на оплату (пример интеграции)
    return {
        "payment_id": payment.id,
        "provider": PAYMENT_PROVIDER,
        "amount": payment.amount,
        "currency": "KZT",
        "pay_url": f"https://pay.example.kz/checkout/{payment.external_id}",
        "webhook_url": "/api/billing/webhook",
    }


@router.get("/mock-confirm")
def mock_confirm(payment_id: str, signature: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Подтверждение оплаты в демо-режиме (проверяется подпись)."""
    payment = db.get(Payment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    if not hmac.compare_digest(signature, _sign(payment.id, payment.amount, "paid")):
        raise HTTPException(status_code=403, detail="Неверная подпись платежа")
    return _apply_payment(db, payment, user)


@router.post("/webhook")
def webhook(payload: WebhookIn, db: Session = Depends(get_db)):
    """Вебхук платёжной системы (Kaspi / CloudPayments / Stripe)."""
    payment = db.get(Payment, payload.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    if not hmac.compare_digest(payload.signature or "", _sign(payment.id, payment.amount, payload.status)):
        raise HTTPException(status_code=403, detail="Неверная подпись")
    user = db.get(User, payment.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if payload.status != "paid":
        payment.status = payload.status
        db.commit()
        return {"ok": True, "status": payment.status}
    return _apply_payment(db, payment, user)


def _apply_payment(db: Session, payment: Payment, user: User) -> dict:
    if payment.status == "paid":
        return {"ok": True, "already": True, "tier": user.tier}
    payment.status = "paid"
    payment.paid_at = datetime.now(timezone.utc)
    extend_subscription(db, user, payment.plan_id)
    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "tier": user.tier,
        "plan": plan_of(user)["name"],
        "expires_at": user.tier_expires_at.isoformat() if user.tier_expires_at else None,
        "message": f"Оплата прошла! Тариф {plan_of(user)['name']} активирован на 30 дней 🎉",
    }


@router.get("/payments")
def my_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.execute(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(50))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id, "plan_id": r.plan_id, "amount": r.amount, "currency": r.currency,
            "status": r.status, "provider": r.provider,
            "created_at": r.created_at.isoformat(), "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        }
        for r in rows
    ]
