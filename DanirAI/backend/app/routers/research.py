"""Deep Research — глубокое исследование темы с поиском в интернете."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agent.research import deep_research
from ..config import MODELS_BY_ID
from ..database import get_db
from ..deps import bump_usage, check_quota, get_current_user, plan_of
from ..models import Chat, Message, User
from ..providers.search import read_page, web_search
from ..schemas import ResearchIn, SearchIn
from ._util import message_to_dict

router = APIRouter(prefix="/api", tags=["research"])


@router.post("/search")
async def search(payload: SearchIn, user: User = Depends(get_current_user)):
    """Быстрый поиск в интернете."""
    results = await web_search(payload.query, max_results=payload.max_results)
    return {"query": payload.query, "results": results}


@router.post("/read")
async def read(payload: dict, user: User = Depends(get_current_user)):
    url = (payload.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Нужен полный URL, начинающийся с http")
    text = await read_page(url, max_chars=int(payload.get("max_chars", 6000)))
    return {"url": url, "text": text, "chars": len(text)}


@router.post("/research")
async def research(payload: ResearchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Полное глубокое исследование: план → поиск → чтение → отчёт."""
    model = MODELS_BY_ID.get(payload.model_id)
    if not model or model["kind"] != "research":
        raise HTTPException(status_code=400, detail="Для исследования используйте danirai-research или danirai-agent")
    if payload.model_id not in plan_of(user).get("models", []):
        raise HTTPException(status_code=402, detail=f"{model['name']} доступна на тарифе Pro")
    check_quota(db, user, "research", "research_per_day")

    result = await deep_research(payload.query, depth=max(1, min(3, payload.depth)))
    bump_usage(db, user.id, "research")

    saved_message = None
    if payload.chat_id:
        chat = db.get(Chat, payload.chat_id)
        if chat and chat.user_id == user.id:
            db.add(Message(chat_id=chat.id, role="user", content=f"🔎 Исследовать: {payload.query}", model_id=payload.model_id))
            msg = Message(
                chat_id=chat.id,
                role="assistant",
                content=result.report,
                model_id=payload.model_id,
                sources=json.dumps(result.sources, ensure_ascii=False),
                tokens=len(result.report) // 4,
            )
            db.add(msg)
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(msg)
            saved_message = message_to_dict(msg)

    return {
        "query": payload.query,
        "report": result.report,
        "sources": result.sources,
        "queries": result.queries,
        "steps": [{"title": s.title, "detail": s.detail, "kind": s.kind} for s in result.steps],
        "message": saved_message,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
