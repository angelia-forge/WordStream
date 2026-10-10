from sqlalchemy.orm import Session

from app.models.setting import AppSetting


class AppSettingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> AppSetting | None:
        return self._session.get(AppSetting, 1)

    def add(self, setting: AppSetting) -> None:
        self._session.add(setting)
        self._session.flush()
