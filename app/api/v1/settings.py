from fastapi import APIRouter

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.schemas.settings import AppSettingRead, AppSettingUpdate
from app.services.settings import AppSettingService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettingRead)
def get_settings(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
) -> AppSettingRead:
    return AppSettingService(uow, config).get()


@router.patch("", response_model=AppSettingRead)
def update_settings(
    changes: AppSettingUpdate,
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
) -> AppSettingRead:
    return AppSettingService(uow, config).update(changes)
