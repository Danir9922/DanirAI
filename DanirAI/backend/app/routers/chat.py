"""Чаты DanirAI: у каждого пользователя свои чаты и своя история."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.runner import run_agent
from ..config import MODELS_BY_ID
from ..database import get_db
from ..deps import bump_usage, check_quota, get_current_user, plan_of
from ..models import Chat, Message, User
from ..providers import smart_chat
from ..schemas import ChatCreate, ChatSendIn, ChatUpdate
from ._util import auto_title, chat_to_dict, message_to_dict

router = APIRouter(prefix="/api/chats", tags=["chats"])
share_router = APIRouter(prefix="/api/share", tags=["chats"])

SYSTEM_PROMPTS = {
    "danirai-1v": "Отвечай кратко, ясно и по делу. Язык ответа — язык пользователя.",
    "danirai-1-pro": (
        "Ты DanirAI-1 PRO. Думай глубоко: рассмотри задачу с разных сторон, "
        "проверь себя, приведи примеры и дай структурированный, подробный ответ."
    ),
    "danirai-research": "Ты аналитик DanirAI Deep Research. Давай развёрнутые ответы с фактами.",
    "danirai-agent": "Ты автономный агент DanirAI. Решай задачу пошагово с помощью инструментов.",
}


def _get_chat(db: Session, user: User, chat_id: str) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return chat


def _check_model(user: User, model_id: str) -> dict:
    model = MODELS_BY_ID.get(model_id)
    if not model:
        raise HTTPException(status_code=400, detail=f"Неизвестная модель: {model_id}")
    allowed = plan_of(user).get("models", [])
    if model_id not in allowed:
        raise HTTPException(
            status_code=402,
            detail=f"Модель {model['name']} доступна на тарифе выше. Ваш тариф: {plan_of(user)['name']}.",
        )
    return model


@router.get("")
def list_chats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chats = (
        db.execute(
            select(Chat)
            .where(Chat.user_id == user.id)
            .order_by(Chat.is_pinned.desc(), Chat.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return [chat_to_dict(c) for c in chats]


@router.post("", status_code=201)
def create_chat(payload: ChatCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model_id = payload.model_id or "danirai-1v"
    if model_id in MODELS_BY_ID:
        _check_model(user, model_id)
    chat = Chat(user_id=user.id, title=payload.title or "Новый чат", model_id=model_id)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat_to_dict(chat)


@router.get("/{chat_id}")
def get_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return chat_to_dict(_get_chat(db, user, chat_id), with_messages=True)


@router.patch("/{chat_id}")
def update_chat(
    chat_id: str, payload: ChatUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    chat = _get_chat(db, user, chat_id)
    if payload.title is not None:
        chat.title = payload.title.strip()[:200] or "Новый чат"
    if payload.model_id:
        _check_model(user, payload.model_id)
        chat.model_id = payload.model_id
    if payload.system_prompt is not None:
        chat.system_prompt = payload.system_prompt.strip()[:2000]
    if payload.is_pinned is not None:
        chat.is_pinned = payload.is_pinned
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return chat_to_dict(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_chat(db, user, chat_id)
    db.delete(chat)
    db.commit()
    return {"ok": True, "id": chat_id}


@router.delete("")
def clear_all_chats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chats = db.execute(select(Chat).where(Chat.user_id == user.id)).scalars().all()
    for c in chats:
        db.delete(c)
    db.commit()
    return {"ok": True, "deleted": len(chats)}


def _history(chat: Chat, limit: int = 20) -> list[dict[str, str]]:
    msgs = [m for m in chat.messages if m.role in ("user", "assistant") and m.content.strip()]
    return [{"role": m.role, "content": m.content} for m in msgs[-limit:]]


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    payload: ChatSendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Главный метод: отправить сообщение и получить ответ модели."""
    chat = _get_chat(db, user, chat_id)
    model_id = payload.model_id or chat.model_id
    model = _check_model(user, model_id)
    check_quota(db, user, "message", "messages_per_day")

    kind = "message" if model["kind"] == "chat" else "research"
    check_quota(db, user, kind, "messages_per_day" if kind == "message" else "research_per_day")

    # сохраняем сообщение пользователя
    user_msg = Message(chat_id=chat.id, role="user", content=payload.content, model_id=model_id)
    db.add(user_msg)
    if chat.title in ("Новый чат", ""):
        chat.title = auto_title(payload.content)
    chat.model_id = model_id
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()

    system = payload.system_prompt or chat.system_prompt or SYSTEM_PROMPTS.get(model_id, "")

    try:
        if model["kind"] == "research":
            trace = await run_agent(payload.content, model_id=model_id)
            text = trace.answer
            reasoning = "\n".join(
                f"[{s.get('tool', s.get('type'))}] {str(s.get('content') or s.get('result') or '')[:300]}"
                for s in trace.steps
                if s.get("type") in ("think", "tool")
            )
            sources = trace.sources
            attachments = trace.images
        else:
            res = await smart_chat(
                _history(chat)[:-1] + [{"role": "user", "content": payload.content}],
                model_id=model_id,
                system=system,
                reasoning=bool(model.get("reasoning")),
                max_tokens=3000 if model.get("reasoning") else 1500,
            )
            text, reasoning, sources, attachments = res.text, res.reasoning, res.sources, res.attachments
    except Exception as exc:  # noqa: BLE001
        err = Message(
            chat_id=chat.id,
            role="assistant",
            content=f"⚠️ DanirAI не смог ответить: {exc}\n\nПопробуйте ещё раз или выберите другую модель.",
            model_id=model_id,
            is_error=True,
        )
        db.add(err)
        db.commit()
        return {"chat": chat_to_dict(chat), "user_message": message_to_dict(user_msg), "message": message_to_dict(err)}

    assistant_msg = Message(
        chat_id=chat.id,
        role="assistant",
        content=text,
        reasoning=reasoning[:8000] if reasoning else "",
        model_id=model_id,
        sources=json.dumps(sources, ensure_ascii=False) if sources else "",
        attachments=json.dumps(attachments, ensure_ascii=False) if attachments else "",
        tokens=len(text) // 4,
    )
    db.add(assistant_msg)
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    bump_usage(db, user.id, kind)
    db.refresh(assistant_msg)

    return {
        "chat": chat_to_dict(chat),
        "user_message": message_to_dict(user_msg),
        "message": message_to_dict(assistant_msg),
    }


@router.post("/{chat_id}/messages/stream")
async def stream_message(
    chat_id: str,
    payload: ChatSendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Потоковый ответ (SSE) — текст появляется по мере генерации."""
    chat = _get_chat(db, user, chat_id)
    model_id = payload.model_id or chat.model_id
    model = _check_model(user, model_id)
    check_quota(db, user, "message", "messages_per_day")

    user_msg = Message(chat_id=chat.id, role="user", content=payload.content, model_id=model_id)
    db.add(user_msg)
    if chat.title in ("Новый чат", ""):
        chat.title = auto_title(payload.content)
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)

    history = _history(chat)
    system = payload.system_prompt or chat.system_prompt or SYSTEM_PROMPTS.get(model_id, "")
    chat_pk, user_pk, model_name = chat.id, user_msg.id, model_id

    async def event_stream():
        import asyncio

        from ..database import SessionLocal

        yield _sse({"type": "start", "user_message": message_to_dict(user_msg)})
        collected: list[str] = []
        try:
            res = await smart_chat(
                history, model_id=model_name, system=system,
                reasoning=bool(model.get("reasoning")), max_tokens=2000,
            )
            text = res.text or ""
            # отдаём текст кусочками — как в ChatGPT
            chunk = 24
            for i in range(0, len(text), chunk):
                piece = text[i : i + chunk]
                collected.append(piece)
                yield _sse({"type": "delta", "text": piece})
                await asyncio.sleep(0.012)
            final_text = "".join(collected)
            db2 = SessionLocal()
            try:
                msg = Message(
                    chat_id=chat_pk, role="assistant", content=final_text,
                    reasoning=res.reasoning[:8000], model_id=model_name,
                    sources=json.dumps(res.sources, ensure_ascii=False) if res.sources else "",
                    tokens=len(final_text) // 4,
                )
                db2.add(msg)
                c = db2.get(Chat, chat_pk)
                if c:
                    c.updated_at = datetime.now(timezone.utc)
                db2.commit()
                db2.refresh(msg)
                out = message_to_dict(msg)
                bump_usage(db2, user.id, "message")
            finally:
                db2.close()
            yield _sse({"type": "done", "message": out})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{chat_id}/regenerate")
async def regenerate(
    chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Перегенерировать последний ответ."""
    chat = _get_chat(db, user, chat_id)
    last_user = next((m for m in reversed(chat.messages) if m.role == "user"), None)
    if not last_user:
        raise HTTPException(status_code=400, detail="В чате нет сообщений пользователя")
    last_answer = next((m for m in reversed(chat.messages) if m.role == "assistant"), None)
    if last_answer:
        db.delete(last_answer)
        db.commit()
    check_quota(db, user, "message", "messages_per_day")
    model = _check_model(user, chat.model_id)
    res = await smart_chat(
        _history(chat), model_id=chat.model_id,
        system=chat.system_prompt or SYSTEM_PROMPTS.get(chat.model_id, ""),
        reasoning=bool(model.get("reasoning")), max_tokens=2500,
    )
    msg = Message(
        chat_id=chat.id, role="assistant", content=res.text, reasoning=res.reasoning[:8000],
        model_id=chat.model_id, tokens=len(res.text) // 4,
    )
    db.add(msg)
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    bump_usage(db, user.id, "message")
    db.refresh(msg)
    return {"message": message_to_dict(msg)}


@router.post("/{chat_id}/share")
def share_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Публичная ссылка на чат (только чтение)."""
    chat = _get_chat(db, user, chat_id)
    payload = {
        "title": chat.title,
        "model_id": chat.model_id,
        "messages": [message_to_dict(m) for m in chat.messages if m.role in ("user", "assistant")],
        "shared_by": user.display_name or "DanirAI user",
        "shared_at": datetime.now(timezone.utc).isoformat(),
    }
    import base64

    token = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode().rstrip("=")
    return {"share_id": token, "url": f"/api/share/{token}"}


@share_router.get("/{share_id}")
def get_shared(share_id: str):
    import base64

    try:
        padding = "=" * (-len(share_id) % 4)
        data = json.loads(base64.urlsafe_b64decode(share_id + padding))
    except Exception:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    return data
