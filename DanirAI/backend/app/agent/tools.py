"""Инструменты агента DanirAI: поиск, чтение страниц, калькулятор, картинки, время."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from ..providers.local_brain import safe_eval
from ..providers.search import read_page, web_search
from ..services.image_service import generate_image

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Ищет информацию в интернете. Используй для свежих новостей, фактов, цен и всего, что может быть неизвестно.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Сколько результатов вернуть (1-10)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_page",
            "description": "Открывает страницу по URL и возвращает её текст. Используй после web_search, чтобы изучить источник.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Адрес страницы"},
                    "max_chars": {"type": "integer", "default": 3000},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Считает математическое выражение. Поддерживает + - * / % ** и функции sqrt, sin, cos, log, abs, round, min, max.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Например: (1250*3)/7 + sqrt(144)"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Рисует изображение по текстовому описанию и возвращает ссылку на файл.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Подробное описание картинки на английском"},
                    "width": {"type": "integer", "default": 1024},
                    "height": {"type": "integer", "default": 1024},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Возвращает текущие дату и время (UTC).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def tool_web_search(query: str, max_results: int = 5) -> dict:
    results = await web_search(query, max_results=int(max_results))
    return {"query": query, "results": results}


async def tool_read_page(url: str, max_chars: int = 3000) -> dict:
    text = await read_page(url, max_chars=int(max_chars))
    return {"url": url, "text": text}


async def tool_calculator(expression: str) -> dict:
    value = safe_eval(expression)
    if value is None:
        return {"expression": expression, "error": "Не удалось вычислить выражение"}
    return {"expression": expression, "result": value}


async def tool_generate_image(prompt: str, width: int = 1024, height: int = 1024) -> dict:
    return await generate_image(prompt, width=int(width), height=int(height))


async def tool_current_time() -> dict:
    return {"utc": datetime.now(timezone.utc).isoformat()}


REGISTRY: dict[str, Callable[..., Any]] = {
    "web_search": tool_web_search,
    "read_page": tool_read_page,
    "calculator": tool_calculator,
    "generate_image": tool_generate_image,
    "current_time": tool_current_time,
}


async def run_tool(name: str, arguments: str | dict) -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"Неизвестный инструмент: {name}"}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            arguments = {"query": arguments}
    try:
        return await fn(**arguments)
    except TypeError as exc:
        return {"error": f"Неверные аргументы: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
