"""Поиск в интернете для DanirAI Deep Research и Agent.

Провайдеры:
- duckduckgo — HTML-версия, без ключа (по умолчанию);
- searxng    — свой инстанс (SEARXNG_URL), JSON;
- brave/serper — если задан ключ.
Плюс извлечение текста со страниц для «чтения» источников.
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse
from typing import Any

import httpx

from ..config import REQUEST_TIMEOUT, SEARXNG_URL, SEARCH_PROVIDER

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def web_search(query: str, max_results: int = 6) -> list[dict[str, Any]]:
    provider = SEARCH_PROVIDER.lower()
    try:
        if provider == "searxng":
            return await _searxng(query, max_results)
        if provider == "brave" and os.getenv("BRAVE_API_KEY"):
            return await _brave(query, max_results)
        if provider == "serper" and os.getenv("SERPER_API_KEY"):
            return await _serper(query, max_results)
        return await _duckduckgo(query, max_results)
    except Exception as exc:  # noqa: BLE001
        return [{"title": "Поиск недоступен", "url": "", "snippet": f"Ошибка поиска: {exc}", "error": True}]


async def _duckduckgo(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = await c.post(url, data={"q": query, "kl": "wt-wt"})
        r.raise_for_status()
        page = r.text

    results: list[dict[str, Any]] = []
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
        page,
        re.S,
    )
    for href, title, snippet in blocks[:max_results]:
        link = _clean_ddg(href)
        if not link:
            continue
        results.append({
            "title": html.unescape(re.sub(r"<[^>]+>", "", title)).strip(),
            "url": link,
            "snippet": html.unescape(re.sub(r"<[^>]+>", "", snippet or "")).strip(),
        })
    if not results:  # запасной парсинг
        for m in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]{10,120})<', page):
            link, title = m.group(1), html.unescape(m.group(2)).strip()
            if "duckduckgo.com" in link:
                continue
            results.append({"title": title, "url": _clean_ddg(link), "snippet": ""})
            if len(results) >= max_results:
                break
    return results


def _clean_ddg(href: str) -> str:
    if href.startswith("//duckduckgo.com/l/?uddg="):
        href = "https:" + href
    if "uddg=" in href:
        qs = urllib.parse.urlparse(href).query
        for k, v in urllib.parse.parse_qsl(qs):
            if k == "uddg":
                return v
    return href if href.startswith("http") else ""


async def _searxng(query: str, max_results: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers={"User-Agent": UA}) as c:
        r = await c.get(SEARXNG_URL, params={"q": query, "format": "json"})
        r.raise_for_status()
        data = r.json()
    return [
        {"title": it.get("title", ""), "url": it.get("url", ""), "snippet": it.get("content", "")}
        for it in data.get("results", [])[:max_results]
    ]


async def _brave(query: str, max_results: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as c:
        r = await c.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": os.getenv("BRAVE_API_KEY", ""), "Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {"title": it.get("title", ""), "url": it.get("url", ""), "snippet": it.get("description", "")}
        for it in data.get("web", {}).get("results", [])[:max_results]
    ]


async def _serper(query: str, max_results: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as c:
        r = await c.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": max_results},
            headers={"X-API-KEY": os.getenv("SERPER_API_KEY", "")},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {"title": it.get("title", ""), "url": it.get("link", ""), "snippet": it.get("snippet", "")}
        for it in data.get("organic", [])[:max_results]
    ]


async def read_page(url: str, max_chars: int = 4000) -> str:
    """Извлекает читаемый текст со страницы."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
            r = await c.get(url)
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return f"[не-текстовый ресурс: {ctype}]"
            raw = r.text
    except Exception as exc:  # noqa: BLE001
        return f"[не удалось открыть: {exc}]"

    raw = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:max_chars]
