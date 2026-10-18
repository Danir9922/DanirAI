"""SQLAlchemy-модели: пользователи, чаты, сообщения, тарифы, оплаты, ассеты."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    tier: Mapped[str] = mapped_column(String(16), default="free")          # free | plus | pro
    tier_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chats: Mapped[list["Chat"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Chat.updated_at.desc()"
    )


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Новый чат")
    model_id: Mapped[str] = mapped_column(String(64), default="danirai-1v")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")           # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text, default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")               # «мысли» PRO-модели
    model_id: Mapped[str] = mapped_column(String(64), default="")
    sources: Mapped[str] = mapped_column(Text, default="")                 # JSON со ссылками
    attachments: Mapped[str] = mapped_column(Text, default="")             # JSON: картинки/видео
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class UsageLog(Base):
    """Счётчик использования по дням — для лимитов тарифов."""

    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)               # YYYY-MM-DD
    kind: Mapped[str] = mapped_column(String(16), index=True)              # message | image | video | research
    count: Mapped[int] = mapped_column(Integer, default=0)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(String(16), default="plus")
    amount: Mapped[int] = mapped_column(Integer, default=0)                # в тенге
    currency: Mapped[str] = mapped_column(String(8), default="KZT")
    status: Mapped[str] = mapped_column(String(16), default="created")     # created | paid | failed | refunded
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    external_id: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Asset(Base):
    """Сгенерированные картинки и видео."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="image")         # image | video
    prompt: Mapped[str] = mapped_column(Text, default="")
    model_id: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(800), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    """Личные API-ключи пользователя (для доступа к DanirAI из своих программ)."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="default")
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
