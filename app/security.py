from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import AuthMode, Settings
from app.exceptions import AppError


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def start_authenticated_session(request: Request) -> str:
    csrf_token = generate_csrf_token()
    request.session.clear()
    request.session.update(
        {
            "authenticated": True,
            "csrf_token": csrf_token,
        }
    )
    return csrf_token


def clear_session(request: Request) -> None:
    request.session.clear()


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
    if settings.app_password is None:
        return False
    return hmac.compare_digest(
        candidate,
        settings.app_password.get_secret_value(),
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

    if request.session.get("authenticated") is not True:
        raise AppError("UNAUTHORIZED", "Authentication required", status_code=401)

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_token = request.headers.get("X-CSRF-Token", "")
        expected_token = request.session.get("csrf_token")
        if not isinstance(expected_token, str) or not hmac.compare_digest(
            csrf_token,
            expected_token,
        ):
            raise AppError("CSRF_FAILED", "Invalid CSRF token", status_code=403)
