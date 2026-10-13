from fastapi import APIRouter, status

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.schemas.study_sessions import (
    OutcomeBatch,
    OutcomeBatchResult,
    StudySessionCreate,
    StudySessionRead,
    StudySessionSummary,
)
from app.services.study_sessions import StudySessionService

router = APIRouter(prefix="/study-sessions", tags=["study sessions"])


@router.post(
    "",
    response_model=StudySessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_study_session(
    command: StudySessionCreate,
    uow: UowDep,
    config: ConfigDep,
    _: AccessDep,
) -> StudySessionRead:
    return StudySessionService(uow, config).create(command)


@router.get("/{session_id}", response_model=StudySessionRead)
def get_study_session(
    session_id: int,
    uow: UowDep,
    config: ConfigDep,
    _: AccessDep,
) -> StudySessionRead:
    return StudySessionService(uow, config).get(session_id)


@router.post(
    "/{session_id}/outcomes/batch",
    response_model=OutcomeBatchResult,
)
def record_study_outcomes(
    session_id: int,
    batch: OutcomeBatch,
    uow: UowDep,
    config: ConfigDep,
    _: AccessDep,
) -> OutcomeBatchResult:
    return StudySessionService(uow, config).record_outcomes(session_id, batch)


@router.post(
    "/{session_id}/finish",
    response_model=StudySessionSummary,
)
def finish_study_session(
    session_id: int,
    uow: UowDep,
    config: ConfigDep,
    _: AccessDep,
) -> StudySessionSummary:
    return StudySessionService(uow, config).finish(session_id)
