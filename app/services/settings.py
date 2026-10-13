from __future__ import annotations

from app.config import Settings
from app.models.setting import AppSetting
from app.schemas.settings import AppSettingRead, AppSettingUpdate
from app.unit_of_work import AbstractUnitOfWork


def get_or_create_setting(
    uow: AbstractUnitOfWork,
    config: Settings,
) -> AppSetting:
    setting = uow.settings.get()
    if setting is None:
        setting = AppSetting(
            timezone=config.app_timezone,
            tts_rate=config.tts_rate,
        )
        uow.settings.add(setting)
    return setting


class AppSettingService:
    def __init__(self, uow: AbstractUnitOfWork, config: Settings) -> None:
        self._uow = uow
        self._config = config

    def get(self) -> AppSettingRead:
        with self._uow:
            setting = self._get_or_create()
            self._uow.commit()
            return AppSettingRead.model_validate(setting)

    def update(self, changes: AppSettingUpdate) -> AppSettingRead:
        with self._uow:
            setting = self._get_or_create()
            values = changes.model_dump(exclude_unset=True, exclude_none=True)
            for field, value in values.items():
                setattr(setting, field, value)
            self._uow.commit()
            return AppSettingRead.model_validate(setting)

    def _get_or_create(self) -> AppSetting:
        return get_or_create_setting(self._uow, self._config)
