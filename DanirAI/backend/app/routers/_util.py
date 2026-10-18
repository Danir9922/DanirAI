"""Общие утилиты сериализации для роутеров."""
from __future__ import annotations

import json
from typing import Any

from ..models import Chat, Message


def _loads(value: str) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


def message_to_dict(msg: Message) -> dict[str, Any]:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "reasoning": msg.reasoning or "",
        "model_id": msg.model_id or "",
        "sources": _loads(msg.sources),
        "attachments": _loads(msg.attachments),
        "tokens": msg.tokens or 0,
        "is_error": bool(msg.is_error),
        "created_at": msg.created_at.isoformat() if msg.created_at else "",
    }


def chat_to_dict(chat: Chat, *, with_messages: bool = False) -> dict[str, Any]:
    data = {
        "id": chat.id,
        "title": chat.title,
        "model_id": chat.model_id,
        "system_prompt": chat.system_prompt or "",
        "is_pinned": chat.is_pinned,
        "created_at": chat.created_at.isoformat() if chat.created_at else "",
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else "",
        "message_count": len(chat.messages),
        "preview": next((m.content[:80] for m in reversed(chat.messages) if m.role == "user"), ""),
    }
    if with_messages:
        data["messages"] = [message_to_dict(m) for m in chat.messages]
    return data


def auto_title(text: str) -> str:
    clean = " ".join(text.split())
    return (clean[:42] + "…") if len(clean) > 43 else clean
