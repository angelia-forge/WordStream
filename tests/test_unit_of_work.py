import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.setting import AppSetting
from app.unit_of_work import SqlAlchemyUnitOfWork


def test_unit_of_work_rolls_back_on_exception(client: TestClient) -> None:
    session_factory = client.app.state.session_factory
    uow = SqlAlchemyUnitOfWork(session_factory)

    with pytest.raises(RuntimeError, match="force rollback"), uow:
        uow.settings.add(AppSetting(timezone="UTC"))
        raise RuntimeError("force rollback")

    with session_factory() as session:
        assert session.scalar(select(AppSetting)) is None
