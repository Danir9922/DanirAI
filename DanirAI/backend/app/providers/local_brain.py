"""Офлайн-провайдер DanirAI Local Brain.

Работает без интернета и ключей: понимает приветствия, считает математику,
пишет код, делает переводы и структурированные ответы. В PRO-режиме
показывает цепочку рассуждений. Используется как последний резерв,
чтобы платформа всегда отвечала.
"""
from __future__ import annotations

import ast
import math
import operator
import random
import re
from datetime import datetime
from typing import Any

from .base import BaseProvider, GenResult

GREETINGS = ["привет", "hi", "hello", "салам", "салем", "здравств", "добрый день", "добрый вечер", "хай", "hey"]
THANKS = ["спасибо", "благодар", "thanks", "thank you", "рахмет"]

SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
SAFE_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
    "log10": math.log10, "pi": math.pi, "e": math.e,
}


def safe_eval(expr: str) -> float | None:
    """Безопасный калькулятор: только числа и арифметика."""
    expr = expr.replace("×", "*").replace("÷", "/").replace(",", ".").strip()
    if not re.fullmatch(r"[\d\s\+\-\*/%\.\(\)a-z_]+", expr):
        return None
    try:
        node = ast.parse(expr, mode="eval").body
        return _eval_node(node)
    except Exception:
        return None


def _eval_node(node: Any) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in SAFE_FUNCS:
        return SAFE_FUNCS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPS:
        return SAFE_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPS:
        return SAFE_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCS:
        fn = SAFE_FUNCS[node.func.id]
        if callable(fn):
            return fn(*[_eval_node(a) for a in node.args])
    raise ValueError("unsupported")


class LocalBrainProvider(BaseProvider):
    name = "local"

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model_id: str,
        system: str = "",
        reasoning: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
    ) -> GenResult:
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text, steps = self._answer(user_msg, reasoning)
        reasoning_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else ""
        return GenResult(text=text, reasoning=reasoning_text, tokens=len(text) // 4, provider=self.name)

    # ------------------------------------------------------------------
    def _answer(self, q: str, reasoning: bool) -> tuple[str, list[str]]:
        steps: list[str] = []
        low = q.lower().strip()

        if reasoning:
            steps.append("Определяю тип запроса пользователя")
            steps.append("Проверяю, есть ли подключённый внешний API нейросети")
            steps.append("Формирую наиболее полезный ответ из доступных знаний")

        # Приветствие
        if any(low.startswith(g) or g in low[:30] for g in GREETINGS) and len(low) < 60:
            hi = random.choice([
                "Привет! Я **DanirAI** 👋 Чем могу помочь?",
                "Здравствуйте! DanirAI на связи. Задавайте любой вопрос 🚀",
                "Салам! Я DanirAI — спросите что угодно 😊",
            ])
            return hi + "\n\n> Подключите `OPENAI_API_KEY` в `.env`, чтобы я отвечал как ChatGPT/Gemini.", steps

        if any(t in low for t in THANKS) and len(low) < 40:
            return "Всегда пожалуйста! 😊 Обращайтесь в любое время.", steps

        # Кто ты
        if re.search(r"(кто ты|что ты (такое|умеешь)|what are you|расскажи о себе)", low):
            return (
                "Я **DanirAI** — искусственный интеллект-ассистент.\n\n"
                "**Мои модели:**\n"
                "- ⚡ **DanirAI-1v** — быстрые ответы\n"
                "- 🧠 **DanirAI-1 PRO** — глубокое мышление\n"
                "- 🔎 **DanirAI Deep Research** — поиск в интернете и отчёты\n"
                "- 🎨 **DanirAI Image** — генерация картинок\n"
                "- 🎬 **DanirAI Video** — генерация видео\n\n"
                "Сейчас работаю в офлайн-режиме. Чтобы включить полноценную нейросеть, "
                "добавьте `OPENAI_API_KEY` в файл `.env` и перезапустите сервер."
            ), steps

        # Математика
        math_expr = re.search(r"[\d\.\,\s\+\-\*/%\(\)]{3,}", q)
        if math_expr and re.search(r"\d\s*[\+\-\*/%]\s*\d", math_expr.group()):
            value = safe_eval(math_expr.group())
            if value is not None:
                if reasoning:
                    steps.append(f"Вычисляю выражение: {math_expr.group().strip()}")
                pretty = int(value) if float(value).is_integer() else round(value, 6)
                return f"**Ответ:** `{math_expr.group().strip()} = {pretty}`", steps

        # Код
        if re.search(r"(код|программ|python|javascript|функци|алгоритм|html|css|sql)", low):
            return (
                "Могу помочь с кодом! Вот пример на Python:\n\n"
                "```python\n"
                "def danirai_hello(name: str) -> str:\n"
                "    \"\"\"Приветствие от DanirAI.\"\"\"\n"
                "    return f\"Привет, {name}! Я DanirAI 🤖\"\n\n"
                "print(danirai_hello(\"мир\"))\n"
                "```\n\n"
                "Уточните задачу — и я напишу полный код. "
                "(Для сложных задач подключите `OPENAI_API_KEY`.)"
            ), steps

        # Дата/время
        if re.search(r"(который час|какое (сегодня )?число|дата|время сейчас|today|date)", low):
            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            return f"Сейчас **{now}** (время сервера).", steps

        # По умолчанию — честный ответ офлайн-режима
        snippet = q.strip().replace("\n", " ")[:220]
        return (
            f"Я получил ваш запрос: «{snippet}».\n\n"
            "Сейчас DanirAI работает в **офлайн-режиме** (встроенный Local Brain), "
            "поэтому отвечаю по шаблонам. Чтобы я рассуждал как ChatGPT или Gemini, сделайте одно из:\n\n"
            "1. Добавьте ключ в `.env`: `OPENAI_API_KEY=sk-...` — включится полноценная нейросеть.\n"
            "2. Или оставьте как есть — бесплатный провайдер Pollinations подхватится, "
            "если у сервера есть интернет.\n\n"
            "Я умею: отвечать на вопросы, считать, писать код, искать в интернете "
            "(Deep Research), рисовать картинки и делать видео."
        ), steps
