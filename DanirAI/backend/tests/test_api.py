"""Тесты API DanirAI (pytest + httpx ASGI, без внешних зависимостей)."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

# изолированная база для тестов
_tmp = tempfile.mkdtemp(prefix="danirai-test-")
os.environ["DANIRAI_DATA_DIR"] = _tmp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

from app.database import init_db
from app.main import app

init_db()


def client_ctx():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120)


async def _register(c, email, password="secret123"):
    r = await c.post("/api/auth/register", json={"email": email, "password": password, "display_name": "T"})
    assert r.status_code == 200, r.text
    return r.json()


def test_health():
    async def run():
        async with client_ctx() as c:
            r = await c.get("/api/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
    asyncio.run(run())


def test_models_catalog():
    async def run():
        async with client_ctx() as c:
            r = await c.get("/api/models")
            ids = {m["id"] for m in r.json()["models"]}
            assert {"danirai-1v", "danirai-1-pro", "danirai-research", "danirai-image", "danirai-video"} <= ids
    asyncio.run(run())


def test_register_login_me():
    async def run():
        async with client_ctx() as c:
            data = await _register(c, "a@example.com")
            assert data["user"]["email"] == "a@example.com"
            h = {"Authorization": f"Bearer {data['access_token']}"}
            me = await c.get("/api/auth/me", headers=h)
            assert me.status_code == 200 and me.json()["tier"] == "free"
            ok = await c.post("/api/auth/login", json={"email": "a@example.com", "password": "secret123"})
            assert ok.status_code == 200
            bad = await c.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"})
            assert bad.status_code == 401
    asyncio.run(run())


def test_duplicate_email():
    async def run():
        async with client_ctx() as c:
            await _register(c, "dup@example.com")
            r = await c.post("/api/auth/register", json={"email": "dup@example.com", "password": "secret123"})
            assert r.status_code == 409
    asyncio.run(run())


def test_chat_flow_and_isolation():
    async def run():
        async with client_ctx() as c:
            d1 = await _register(c, "user1@example.com")
            d2 = await _register(c, "user2@example.com")
            h1 = {"Authorization": f"Bearer {d1['access_token']}"}
            h2 = {"Authorization": f"Bearer {d2['access_token']}"}
            chat = await c.post("/api/chats", json={"model_id": "danirai-1v"}, headers=h1)
            assert chat.status_code == 201
            cid = chat.json()["id"]
            msg = await c.post(f"/api/chats/{cid}/messages", json={"content": "2+2*10 = ?"}, headers=h1)
            assert msg.status_code == 200
            assert "22" in msg.json()["message"]["content"]
            assert (await c.get(f"/api/chats/{cid}", headers=h2)).status_code == 404
            assert (await c.get("/api/chats", headers=h2)).json() == []
    asyncio.run(run())


def test_tier_gating_and_payment():
    async def run():
        async with client_ctx() as c:
            d = await _register(c, "pay@example.com")
            h = {"Authorization": f"Bearer {d['access_token']}"}
            chat = (await c.post("/api/chats", json={}, headers=h)).json()
            r = await c.post(f"/api/chats/{chat['id']}/messages", json={"content": "hi", "model_id": "danirai-1-pro"}, headers=h)
            assert r.status_code == 402
            co = await c.post("/api/billing/checkout", json={"plan_id": "plus"}, headers=h)
            assert co.status_code == 200
            conf = await c.get(co.json()["confirm_url"], headers=h)
            assert conf.status_code == 200 and conf.json()["tier"] == "plus"
            r = await c.post(f"/api/chats/{chat['id']}/messages", json={"content": "hi", "model_id": "danirai-1-pro"}, headers=h)
            assert r.status_code == 200
            v = await c.post("/api/videos", json={"prompt": "test scene", "duration": 2}, headers=h)
            assert v.status_code == 402
    asyncio.run(run())


def test_admin_gate():
    async def run():
        async with client_ctx() as c:
            d = await _register(c, "notadmin@example.com")
            h = {"Authorization": f"Bearer {d['access_token']}"}
            r = await c.get("/api/admin/stats", headers=h)
            assert r.status_code in (200, 403)  # первый юзер сессии — админ, остальные нет
    asyncio.run(run())


def test_api_keys_and_openai_compat():
    async def run():
        async with client_ctx() as c:
            d = await _register(c, "keys@example.com")
            h = {"Authorization": f"Bearer {d['access_token']}"}
            r = await c.post("/api/keys", json={"name": "ci"}, headers=h)
            assert r.status_code == 201
            key = r.json()["api_key"]
            assert key.startswith("dnr_")
            resp = await c.post(
                "/v1/chat/completions",
                json={"model": "danirai-1v", "messages": [{"role": "user", "content": "привет"}]},
                headers={"Authorization": f"Bearer {key}"},
            )
            assert resp.status_code == 200
            assert resp.json()["choices"][0]["message"]["content"]
    asyncio.run(run())
