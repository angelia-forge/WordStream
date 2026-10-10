from __future__ import annotations

import hmac
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import AuthMode
from app.dependencies import ConfigDep
from app.security import (
    LoginRateLimiter,
    clear_session,
    start_authenticated_session,
    verify_shared_password,
)

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, config: ConfigDep) -> Response:
    authenticated = request.session.get("authenticated") is True
    if config.auth_mode is AuthMode.PASSWORD and not authenticated:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "csrf_token": request.session.get("csrf_token", ""),
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, config: ConfigDep) -> Response:
    if config.auth_mode is AuthMode.DISABLED:
        return RedirectResponse("/", status_code=303)
    if request.session.get("authenticated") is True:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    config: ConfigDep,
    password: str = Form(),
) -> Response:
    client_id = request.client.host if request.client else "unknown"
    limiter = cast(LoginRateLimiter, request.app.state.login_rate_limiter)
    limiter.ensure_allowed(client_id)
    if not verify_shared_password(password, config):
        limiter.record_failure(client_id)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "密码不正确"},
            status_code=401,
        )

    limiter.clear(client_id)
    start_authenticated_session(request)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(),
) -> RedirectResponse:
    expected_token = request.session.get("csrf_token")
    if not isinstance(expected_token, str) or not hmac.compare_digest(
        csrf_token,
        expected_token,
    ):
        return RedirectResponse("/", status_code=303)
    clear_session(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/service-worker.js")
def service_worker() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )
