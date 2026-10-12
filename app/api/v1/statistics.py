from fastapi import APIRouter

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.schemas.statistics import StatisticsSummary
from app.services.statistics import StatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsSummary)
def get_statistics(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
) -> StatisticsSummary:
    return StatisticsService(uow, config).summary()
