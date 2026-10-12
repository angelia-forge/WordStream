from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.settings import AppSettingRepository
from app.repositories.vocabularies import VocabularyRepository


class AbstractUnitOfWork(ABC):
    settings: AppSettingRepository
    vocabularies: VocabularyRepository

    @abstractmethod
    def __enter__(self) -> AbstractUnitOfWork:
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        self.settings = AppSettingRepository(self.session)
        self.vocabularies = VocabularyRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
