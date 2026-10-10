from typing import Literal, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.dependencies import ConfigDep

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    application: str
    version: str
    database: Literal["ok", "error"]
    migration: Literal["current", "uninitialized"]
    revision: str | None


@router.get("", response_model=HealthResponse)
def health(request: Request, config: ConfigDep) -> HealthResponse:
    engine = cast(Engine, request.app.state.engine)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            table_names = inspect(connection).get_table_names()
            if "alembic_version" not in table_names:
                return HealthResponse(
                    status="degraded",
                    application=config.app_name,
                    version=config.app_version,
                    database="ok",
                    migration="uninitialized",
                    revision=None,
                )
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
    except SQLAlchemyError:
        return HealthResponse(
            status="degraded",
            application=config.app_name,
            version=config.app_version,
            database="error",
            migration="uninitialized",
            revision=None,
        )

    return HealthResponse(
        status="ok",
        application=config.app_name,
        version=config.app_version,
        database="ok",
        migration="current",
        revision=revision,
    )
