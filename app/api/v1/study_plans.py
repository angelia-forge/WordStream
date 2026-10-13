from fastapi import APIRouter

from app.dependencies import AccessDep, UowDep
from app.schemas.study_plans import StudyPlanRead, StudyPlanUpdate
from app.services.study_plans import StudyPlanService

router = APIRouter(prefix="/vocabularies", tags=["study plans"])


@router.get("/{vocabulary_id}/plan", response_model=StudyPlanRead)
def get_study_plan(
    vocabulary_id: int,
    uow: UowDep,
    _: AccessDep,
) -> StudyPlanRead:
    return StudyPlanService(uow).get_plan(vocabulary_id)


@router.put("/{vocabulary_id}/plan", response_model=StudyPlanRead)
def upsert_study_plan(
    vocabulary_id: int,
    update: StudyPlanUpdate,
    uow: UowDep,
    _: AccessDep,
) -> StudyPlanRead:
    return StudyPlanService(uow).upsert_plan(vocabulary_id, update)
