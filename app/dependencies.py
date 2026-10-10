from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.security import authorize_request
from app.unit_of_work import AbstractUnitOfWork, SqlAlchemyUnitOfWork


def get_config(request: Request) -> Settings:
    return cast(Settings, request.app.state.config)


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return cast(sessionmaker[Session], request.app.state.session_factory)


def get_session(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    with session_factory() as session:
        yield session


def get_uow(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> AbstractUnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory)


def require_access(
    request: Request,
    config: Annotated[Settings, Depends(get_config)],
) -> None:
    authorize_request(request, config)


ConfigDep = Annotated[Settings, Depends(get_config)]
SessionDep = Annotated[Session, Depends(get_session)]
UowDep = Annotated[AbstractUnitOfWork, Depends(get_uow)]
AccessDep = Annotated[None, Depends(require_access)]
