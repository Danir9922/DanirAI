"""Агент DanirAI: инструменты, глубокое исследование, автономный запуск."""
from .research import ResearchResult, deep_research
from .runner import AgentTrace, run_agent
from .tools import REGISTRY, TOOL_SCHEMAS, run_tool

__all__ = [
    "REGISTRY",
    "TOOL_SCHEMAS",
    "run_tool",
    "deep_research",
    "ResearchResult",
    "run_agent",
    "AgentTrace",
]
