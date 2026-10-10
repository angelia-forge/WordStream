from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as api_v1_router
from app.config import Settings, get_settings
from app.db import create_database_engine, create_session_factory
from app.exceptions import register_exception_handlers
from app.logging import configure_logging
from app.middleware import request_id_middleware
from app.security import LoginRateLimiter


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

    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()
