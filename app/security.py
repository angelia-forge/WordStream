from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash

from app.config import AuthMode, Settings
from app.exceptions import AppError

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class SessionData:
    csrf_token: str


class SessionManager:
    def __init__(self, settings: Settings) -> None:
        if settings.secret_key is None:
            raise ValueError("A secret key is required for signed sessions")
        self._serializer = URLSafeTimedSerializer(
            settings.secret_key.get_secret_value(),
            salt="wordstream-session",
        )
        self._max_age = settings.session_max_age_seconds

    def create(self) -> tuple[str, SessionData]:
        data = SessionData(csrf_token=secrets.token_urlsafe(24))
        token = self._serializer.dumps(
            {"authenticated": True, "csrf_token": data.csrf_token}
        )
        return token, data

    def load(self, token: str) -> SessionData | None:
        try:
            payload = self._serializer.loads(token, max_age=self._max_age)
        except (BadSignature, SignatureExpired):
            return None
        if payload.get("authenticated") is not True:
            return None
        csrf_token = payload.get("csrf_token")
        if not isinstance(csrf_token, str):
            return None
        return SessionData(csrf_token=csrf_token)


class LoginRateLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def ensure_allowed(self, client_id: str) -> None:
        now = time.monotonic()
        failures = self._failures[client_id]
        while failures and now - failures[0] >= self._window_seconds:
            failures.popleft()
        if len(failures) >= self._limit:
            raise AppError(
                "RATE_LIMITED",
                "Too many login attempts",
                status_code=429,
            )

    def record_failure(self, client_id: str) -> None:
        self._failures[client_id].append(time.monotonic())

    def clear(self, client_id: str) -> None:
        self._failures.pop(client_id, None)


def verify_shared_password(candidate: str, settings: Settings) -> bool:
    if settings.app_password_hash is None:
        return False
    return password_hash.verify(
        candidate,
        settings.app_password_hash.get_secret_value(),
    )


def authorize_request(request: Request, settings: Settings) -> None:
    if settings.auth_mode is AuthMode.DISABLED:
        return

    api_key = request.headers.get("X-API-Key")
    if (
        api_key
        and settings.app_api_key is not None
        and hmac.compare_digest(api_key, settings.app_api_key.get_secret_value())
    ):
        return

    cookie = request.cookies.get(settings.session_cookie_name)
    session = SessionManager(settings).load(cookie) if cookie else None
    if session is None:
        raise AppError("UNAUTHORIZED", "Authentication required", status_code=401)

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(csrf_token, session.csrf_token):
            raise AppError("CSRF_FAILED", "Invalid CSRF token", status_code=403)
