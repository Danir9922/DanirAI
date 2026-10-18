"""DanirAI Agent — автономный агент с инструментами.

Работает двумя способами:
1. Если подключён OpenAI-совместимый API — нативный function calling.
2. Иначе — текстовый протокол ReAct (ACTION / FINAL ANSWER), который
   понимает любой LLM-провайдер, включая бесплатный Pollinations.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..providers import openai_provider, smart_chat
from .tools import REGISTRY, TOOL_SCHEMAS, run_tool

AGENT_SYSTEM = """Ты — DanirAI Agent, автономный ИИ-агент. Ты решаешь задачу пользователя пошагово,
используя инструменты: web_search (поиск в интернете), read_page (чтение страницы),
calculator (вычисления), generate_image (рисование картинок), current_time (время).

Правила:
1. Сначала коротко напиши план (что нужно сделать).
2. Для каждого шага выдай СТРОКУ действия в формате:
ACTION: имя_инструмента {"параметр": "значение"}
3. После получения результата (OBSERVATION) продолжай рассуждение и выдавай следующее ACTION.
4. Когда задача решена, напиши финальный ответ в формате:
FINAL ANSWER:
<твой подробный ответ на языке пользователя, в markdown>

Никогда не выдумывай факты, если можешь проверить их через web_search.
Делай не более 6 действий, затем обязательно выдай FINAL ANSWER."""


@dataclass
class AgentTrace:
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    tools_used: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


ACTION_RE = re.compile(r"ACTION:\s*([a-z_]+)\s*(\{[\s\S]*?\})?\s*$", re.MULTILINE)
FINAL_RE = re.compile(r"FINAL ANSWER:\s*([\s\S]+)", re.IGNORECASE)


def _parse_action(text: str) -> tuple[str, dict] | None:
    m = ACTION_RE.search(text)
    if not m:
        return None
    name = m.group(1)
    args: dict = {}
    if m.group(2):
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            args = {"query": m.group(2).strip("{}\"' ")}
    return (name, args) if name in REGISTRY else None


async def run_agent(task: str, *, model_id: str = "danirai-agent", max_steps: int = 6) -> AgentTrace:
    trace = AgentTrace()
    trace.steps.append({"type": "task", "content": task})

    if openai_provider() is not None:
        try:
            return await _run_with_native_tools(task, model_id, max_steps, trace)
        except Exception as exc:  # noqa: BLE001
            trace.steps.append({"type": "warning", "content": f"Нативные инструменты недоступны ({exc}), переключаюсь на текстовый протокол"})

    return await _run_react(task, model_id, max_steps, trace)


async def _run_with_native_tools(task: str, model_id: str, max_steps: int, trace: AgentTrace) -> AgentTrace:
    provider = openai_provider()
    messages: list[dict] = [{"role": "user", "content": task}]
    for _ in range(max_steps + 1):
        res = await provider.chat(  # type: ignore[union-attr]
            messages, model_id=model_id, system=AGENT_SYSTEM, reasoning=True, max_tokens=2000, tools=TOOL_SCHEMAS
        )
        tool_calls = [a for a in res.attachments if a.get("type") == "tool_calls"]
        if not tool_calls:
            trace.answer = res.text
            trace.steps.append({"type": "answer", "content": res.text})
            break
        calls = tool_calls[0]["data"]
        messages.append({"role": "assistant", "content": res.text or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            out = await run_tool(name, fn.get("arguments", "{}"))
            _collect(out, name, trace)
            trace.tools_used.append(name)
            trace.steps.append({"type": "tool", "tool": name, "args": fn.get("arguments", ""), "result": _short(out)})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(out, ensure_ascii=False)[:4000],
            })
    if not trace.answer:
        trace.answer = "Агент завершил работу, но не сформировал итоговый ответ."
    return trace


async def _run_react(task: str, model_id: str, max_steps: int, trace: AgentTrace) -> AgentTrace:
    messages: list[dict[str, str]] = [{"role": "user", "content": task}]
    answer = ""

    for step in range(max_steps):
        res = await smart_chat(
            messages, model_id=model_id, system=AGENT_SYSTEM, reasoning=True, temperature=0.3, max_tokens=1200
        )
        text = res.text.strip()
        trace.steps.append({"type": "think", "content": text[:1200]})

        final = FINAL_RE.search(text)
        action = _parse_action(text)

        if final and not action:
            answer = final.group(1).strip()
            break
        if not action:
            answer = text
            break

        name, args = action
        trace.tools_used.append(name)
        out = await run_tool(name, args)
        _collect(out, name, trace)
        trace.steps.append({"type": "tool", "tool": name, "args": args, "result": _short(out)})
        messages.append({"role": "assistant", "content": text})
        messages.append({
            "role": "user",
            "content": f"OBSERVATION ({name}):\n{json.dumps(out, ensure_ascii=False)[:3000]}\n\n"
                       "Продолжи. Выдай следующее ACTION или FINAL ANSWER.",
        })

    if not answer:
        answer = "Агент выполнил шаги, но не успел сформировать итоговый ответ. Уточните задачу."
    trace.answer = answer
    trace.steps.append({"type": "answer", "content": answer})
    return trace


def _collect(out: dict, tool_name: str, trace: AgentTrace) -> None:
    if not isinstance(out, dict):
        return
    if tool_name == "web_search":
        for r in out.get("results", [])[:6]:
            if r.get("url") and r["url"] not in {s.get("url") for s in trace.sources}:
                trace.sources.append({"title": r.get("title", ""), "url": r["url"], "snippet": r.get("snippet", "")})
    if tool_name == "generate_image" and out.get("url"):
        trace.images.append({"kind": "image", "url": out["url"], "prompt": out.get("prompt", "")})


def _short(out: Any, limit: int = 700) -> str:
    text = json.dumps(out, ensure_ascii=False) if not isinstance(out, str) else out
    return text[:limit] + ("…" if len(text) > limit else "")
