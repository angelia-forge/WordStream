from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.schemas.statistics import TodayReviewsRead
from app.services.statistics import StatisticsService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/today", response_model=TodayReviewsRead)
def get_today_reviews(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
    vocabulary_id: Annotated[int | None, Query(gt=0)] = None,
) -> TodayReviewsRead:
    return StatisticsService(uow, config).reviews_today(vocabulary_id=vocabulary_id)
