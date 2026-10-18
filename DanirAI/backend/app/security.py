"""Безопасность: хеширование паролей и подписанные токены сессии."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import ACCESS_TOKEN_TTL_MIN, SECRET_KEY

# --- Пароли ----------------------------------------------------------------
try:  # bcrypt, если установлен
    from passlib.context import CryptContext

    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return _pwd.hash(password)

    def verify_password(password: str, hashed: str) -> bool:
        try:
            return _pwd.verify(password, hashed)
        except Exception:
            return False

except Exception:  # запасной вариант — pbkdf2 (всегда доступен)
    def hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
        return f"pbkdf2${salt}${digest}"

    def verify_password(password: str, hashed: str) -> bool:
        try:
            scheme, salt, digest = hashed.split("$")
            if scheme != "pbkdf2":
                return False
            check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
            return hmac.compare_digest(check, digest)
        except Exception:
            return False


# --- Токены сессии (подписанный JWT-подобный токен) -------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(subject: str, extra: dict | None = None, ttl_minutes: int = ACCESS_TOKEN_TTL_MIN) -> str:
    payload = {"sub": subject, "exp": int(time.time()) + ttl_minutes * 60, "jti": secrets.token_hex(8)}
    if extra:
        payload.update(extra)
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def decode_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def hash_api_key(key: str) -> str:
    return hashlib.sha256((SECRET_KEY + key).encode()).hexdigest()


def new_api_key() -> str:
    return "dnr_" + secrets.token_urlsafe(32)
