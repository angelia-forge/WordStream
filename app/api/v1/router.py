from fastapi import APIRouter

from app.api.v1 import (
    auth,
    health,
    settings,
    statistics,
    study_plans,
    study_sessions,
    vocabularies,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(settings.router)
router.include_router(statistics.router)
router.include_router(study_plans.router)
router.include_router(study_sessions.router)
router.include_router(vocabularies.router)
