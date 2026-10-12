from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import AuthMode
from app.dependencies import ConfigDep, UowDep
from app.security import (
    LoginRateLimiter,
    clear_session,
    start_authenticated_session,
    verify_shared_password,
)
from app.services.statistics import StatisticsService
from app.services.vocabularies import VocabularyService

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, config: ConfigDep) -> Response:
    redirect = _login_redirect(request, config)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "csrf_token": request.session.get("csrf_token", ""),
        },
    )


@router.get("/vocabularies/import", response_class=HTMLResponse)
def import_page(request: Request, config: ConfigDep) -> Response:
    redirect = _login_redirect(request, config)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="vocabulary_import.html",
        context={"csrf_token": request.session.get("csrf_token", "")},
    )


@router.get("/vocabularies", response_class=HTMLResponse)
def vocabulary_list(
    request: Request,
    config: ConfigDep,
    uow: UowDep,
    page: Annotated[int, Query(ge=1)] = 1,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    redirect = _login_redirect(request, config)
    if redirect is not None:
        return redirect
    page_size = 12
    vocabularies = VocabularyService(uow).list_vocabularies(
        page=page,
        page_size=page_size,
        query=q,
        sort="created_at",
        order="desc",
    )
    return templates.TemplateResponse(
        request=request,
        name="vocabulary_list.html",
        context={
            "csrf_token": request.session.get("csrf_token", ""),
            "vocabularies": vocabularies,
            "q": q or "",
            "previous_url": (
                _page_url(
                    "/vocabularies",
                    page - 1,
                    q=q,
                )
                if page > 1
                else None
            ),
            "next_url": (
                _page_url(
                    "/vocabularies",
                    page + 1,
                    q=q,
                )
                if page * page_size < vocabularies.total
                else None
            ),
        },
    )


@router.get("/vocabularies/{vocabulary_id}", response_class=HTMLResponse)
def vocabulary_detail(
    vocabulary_id: int,
    request: Request,
    config: ConfigDep,
    uow: UowDep,
    page: Annotated[int, Query(ge=1)] = 1,
    q: Annotated[str | None, Query(max_length=500)] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["term", "created_at"] = "term",
    order: Literal["asc", "desc"] = "asc",
) -> Response:
    redirect = _login_redirect(request, config)
    if redirect is not None:
        return redirect
    service = VocabularyService(uow)
    vocabulary = service.get_vocabulary(vocabulary_id)
    entries = service.list_entries(
        vocabulary_id,
        page=page,
        page_size=20,
        query=q,
        tag=tag,
        sort=sort,
        order=order,
    )
    tags = service.list_tags(vocabulary_id)
    return templates.TemplateResponse(
        request=request,
        name="vocabulary_detail.html",
        context={
            "csrf_token": request.session.get("csrf_token", ""),
            "vocabulary": vocabulary,
            "entries": entries,
            "tags": tags,
            "q": q or "",
            "selected_tag": tag or "",
            "sort": sort,
            "order": order,
            "previous_url": (
                _page_url(
                    f"/vocabularies/{vocabulary_id}",
                    page - 1,
                    q=q,
                    tag=tag,
                    sort=sort,
                    order=order,
                )
                if page > 1
                else None
            ),
            "next_url": (
                _page_url(
                    f"/vocabularies/{vocabulary_id}",
                    page + 1,
                    q=q,
                    tag=tag,
                    sort=sort,
                    order=order,
                )
                if page * entries.page_size < entries.total
                else None
            ),
        },
    )


@router.get("/statistics", response_class=HTMLResponse)
def statistics_page(
    request: Request,
    config: ConfigDep,
    uow: UowDep,
) -> Response:
    redirect = _login_redirect(request, config)
    if redirect is not None:
        return redirect
    summary = StatisticsService(uow, config).summary()
    return templates.TemplateResponse(
        request=request,
        name="statistics.html",
        context={
            "csrf_token": request.session.get("csrf_token", ""),
            "summary": summary,
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


def _login_redirect(
    request: Request,
    config: ConfigDep,
) -> RedirectResponse | None:
    authenticated = request.session.get("authenticated") is True
    if config.auth_mode is AuthMode.PASSWORD and not authenticated:
        return RedirectResponse("/login", status_code=303)
    return None


def _page_url(path: str, page: int, **params: str | None) -> str:
    query = {
        "page": page,
        **{key: value for key, value in params.items() if value},
    }
    return f"{path}?{urlencode(query)}"
