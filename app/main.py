from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as api_v1_router
from app.config import Settings, get_settings
from app.db import create_database_engine, create_session_factory
from app.exceptions import register_exception_handlers
from app.logging import configure_logging
from app.middleware import request_id_middleware
from app.security import LoginRateLimiter
from app.web.router import STATIC_DIR
from app.web.router import router as web_router


def create_app(config: Settings | None = None) -> FastAPI:
    resolved_config = config or get_settings()
    configure_logging()
    engine = create_database_engine(resolved_config)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        yield
        engine.dispose()

    app = FastAPI(
        title=resolved_config.app_name,
        version=resolved_config.app_version,
        lifespan=lifespan,
    )
    app.state.config = resolved_config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.login_rate_limiter = LoginRateLimiter()

    session_secret = (
        resolved_config.secret_key.get_secret_value()
        if resolved_config.secret_key is not None
        else secrets.token_urlsafe(32)
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie=resolved_config.session_cookie_name,
        max_age=resolved_config.session_max_age_seconds,
        same_site="lax",
        https_only=resolved_config.secure_cookies,
    )
    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(api_v1_router)
    app.include_router(web_router)
    return app


app = create_app()
