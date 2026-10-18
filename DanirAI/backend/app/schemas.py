"""Pydantic-схемы запросов и ответов."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# --- Auth ------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str
    bio: str
    tier: str
    tier_expires_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Chats -----------------------------------------------------------------
class ChatCreate(BaseModel):
    title: str | None = None
    model_id: str = "danirai-1v"


class ChatUpdate(BaseModel):
    title: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    is_pinned: bool | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    reasoning: str = ""
    model_id: str = ""
    sources: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    tokens: int = 0
    is_error: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ChatOut(BaseModel):
    id: str
    title: str
    model_id: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    preview: str = ""

    class Config:
        from_attributes = True


class ChatFull(BaseModel):
    chat: ChatOut
    messages: list[MessageOut]


class ChatSendIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model_id: str | None = None
    system_prompt: str | None = None
    stream: bool = False


# --- Генерация -------------------------------------------------------------
class ImageGenIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=1000)
    model_id: str = "danirai-image"
    width: int = 1024
    height: int = 1024
    chat_id: str | None = None


class VideoGenIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=1000)
    model_id: str = "danirai-video"
    duration: int = 5
    chat_id: str | None = None


class AssetOut(BaseModel):
    id: str
    kind: str
    prompt: str
    model_id: str
    url: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Исследование / поиск --------------------------------------------------
class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    max_results: int = 6


class ResearchIn(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    model_id: str = "danirai-research"
    chat_id: str | None = None
    depth: int = 2  # 1 — быстрый обзор, 2 — стандарт, 3 — глубокий


# --- Оплата ----------------------------------------------------------------
class CheckoutIn(BaseModel):
    plan_id: str
    payment_method: str = "card"


class PaymentOut(BaseModel):
    id: str
    plan_id: str
    amount: int
    currency: str
    status: str
    provider: str
    created_at: datetime
    paid_at: datetime | None

    class Config:
        from_attributes = True


class WebhookIn(BaseModel):
    payment_id: str
    status: str = "paid"
    signature: str = ""


# --- API-ключи -------------------------------------------------------------
class ApiKeyCreate(BaseModel):
    name: str = "default"


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None

    class Config:
        from_attributes = True
