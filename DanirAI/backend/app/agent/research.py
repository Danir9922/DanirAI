"""DanirAI Deep Research — агент глубокого исследования.

План → параллельный поиск по подзапросам → чтение лучших источников →
синтез структурированного отчёта со списком источников.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..providers import smart_chat
from ..providers.search import read_page, web_search

SUBQUERY_SYSTEM = (
    "Ты — планировщик исследования DanirAI. По теме пользователя верни ТОЛЬКО JSON-массив "
    'из 3-5 коротких поисковых запросов на разных языках (русский/английский), без пояснений. '
    'Пример: ["запрос 1", "query 2 in english", "запрос 3"]'
)

REPORT_SYSTEM = (
    "Ты — DanirAI Deep Research, аналитик-исследователь. Напиши подробный, хорошо структурированный "
    "отчёт на языке пользователя, используя ТОЛЬКО предоставленные материалы поиска. "
    "Формат: ## Кратко (3-5 пунктов) → ## Подробности (разделы с подзаголовками) → "
    "## Ключевые факты и цифры → ## Выводы → ## Источники (список ссылок). "
    "Указывай ссылки в тексте как [1], [2]. Если данных не хватает — честно напиши об этом."
)


@dataclass
class ResearchStep:
    title: str
    detail: str = ""
    kind: str = "info"


@dataclass
class ResearchResult:
    report: str = ""
    steps: list[ResearchStep] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)


def _extract_json_array(text: str) -> list[str]:
    m = re.search(r"\[[\s\S]*?\]", text)
    if not m:
        return []
    try:
        import json

        data = json.loads(m.group())
        return [str(x).strip() for x in data if str(x).strip()][:5]
    except Exception:
        return []


async def plan_queries(topic: str, depth: int = 2) -> list[str]:
    n = {1: 2, 2: 3, 3: 5}.get(depth, 3)
    try:
        res = await smart_chat(
            [{"role": "user", "content": f"Тема исследования: {topic}\n\nСоставь {n} поисковых запросов."}],
            model_id="danirai-research",
            system=SUBQUERY_SYSTEM,
            temperature=0.4,
            max_tokens=400,
        )
        queries = _extract_json_array(res.text)
    except Exception:
        queries = []
    if not queries:
        queries = [topic, f"{topic} подробно", f"{topic} latest facts"]
    return queries[:n]


async def gather_sources(queries: list[str], per_query: int = 4) -> tuple[list[dict], list[str]]:
    all_results: list[dict] = []
    seen: set[str] = set()
    searches = await asyncio.gather(*[web_search(q, per_query) for q in queries], return_exceptions=True)
    for q, res in zip(queries, searches):
        if isinstance(res, Exception):
            continue
        for item in res:
            url = item.get("url", "")
            if not url or url in seen or item.get("error"):
                continue
            seen.add(url)
            item["query"] = q
            all_results.append(item)
    return all_results[: per_query * len(queries)], list(seen)


async def read_top_sources(sources: list[dict], limit: int = 5, chars: int = 2500) -> list[dict]:
    async def one(src: dict) -> dict:
        text = await read_page(src["url"], max_chars=chars)
        return {**src, "content": text}

    read = await asyncio.gather(*[one(s) for s in sources[:limit]], return_exceptions=True)
    out = []
    for r in read:
        if isinstance(r, dict) and r.get("content") and not r["content"].startswith("["):
            out.append(r)
    return out


async def deep_research(
    topic: str,
    depth: int = 2,
    on_step: Callable[[str, str], Awaitable[None] | None] | None = None,
) -> ResearchResult:
    result = ResearchResult()

    async def step(title: str, detail: str = "", kind: str = "info") -> None:
        result.steps.append(ResearchStep(title=title, detail=detail, kind=kind))
        if on_step:
            r = on_step(title, detail)
            if asyncio.iscoroutine(r):
                await r

    await step("📋 Составляю план исследования", f"Тема: {topic}")
    queries = await plan_queries(topic, depth)
    result.queries = queries
    await step("🔍 Ищу в интернете", "; ".join(queries))

    per_query = {1: 3, 2: 4, 3: 6}.get(depth, 4)
    sources, _ = await gather_sources(queries, per_query)
    await step(f"📄 Найдено источников: {len(sources)}", ", ".join(s["url"] for s in sources[:5]))

    read_limit = {1: 2, 2: 4, 3: 7}.get(depth, 4)
    chars = {1: 1500, 2: 2500, 3: 3500}.get(depth, 2500)
    deep = await read_top_sources(sources, read_limit, chars)
    await step("📖 Читаю содержимое страниц", f"Изучено {len(deep)} источников")

    context_blocks = []
    for i, src in enumerate(deep or sources[:8], start=1):
        body = src.get("content") or src.get("snippet", "")
        context_blocks.append(f"[{i}] {src.get('title','')}\nURL: {src.get('url','')}\n{body[:chars]}")
    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(материалы не найдены)"

    await step("🧠 Анализирую и синтезирую отчёт")
    used = deep or sources[:8]
    numbered = [
        {"title": s.get("title", ""), "url": s.get("url", ""), "snippet": s.get("snippet", "")}
        for s in used
    ]
    prompt = f"Тема исследования: {topic}\n\nМатериалы из интернета:\n{context}\n\nНапиши полный отчёт."
    try:
        res = await smart_chat(
            [{"role": "user", "content": prompt}],
            model_id="danirai-research",
            system=REPORT_SYSTEM,
            reasoning=True,
            temperature=0.4,
            max_tokens=3000,
        )
        result.report = res.text
        result.steps[-1].detail = res.reasoning[:300] if res.reasoning else ""
    except Exception as exc:  # noqa: BLE001
        result.report = _fallback_report(topic, numbered, exc)

    if not result.report.strip():
        result.report = _fallback_report(topic, numbered, None)

    result.sources = numbered
    await step("✅ Исследование завершено", f"Источников в отчёте: {len(numbered)}")
    return result


def _fallback_report(topic: str, sources: list[dict], error: Exception | None) -> str:
    lines = [f"## 🔎 Отчёт по теме: {topic}", "", "### Кратко"]
    if error:
        lines.append(f"> Модель синтеза недоступна ({error}). Ниже — собранные материалы из интернета.")
    for i, s in enumerate(sources, 1):
        lines.append(f"- **[{i}] {s.get('title','(без названия)')}** — {s.get('snippet','')[:220]}")
    lines += ["", "### Источники"]
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. [{s.get('title','')[:80]}]({s.get('url','')})")
    if not sources:
        lines.append("_Интернет-поиск сейчас недоступен. Проверьте подключение сервера._")
    return "\n".join(lines)
