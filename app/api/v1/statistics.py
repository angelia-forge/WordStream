from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.schemas.statistics import StatisticsSummary, TodayStatisticsRead
from app.services.statistics import StatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsSummary)
def get_statistics(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
) -> StatisticsSummary:
    return StatisticsService(uow, config).summary()


@router.get("/today", response_model=TodayStatisticsRead)
def get_today_statistics(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
    vocabulary_id: Annotated[int | None, Query(gt=0)] = None,
) -> TodayStatisticsRead:
    return StatisticsService(uow, config).today(vocabulary_id=vocabulary_id)
