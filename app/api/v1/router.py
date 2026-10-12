from fastapi import APIRouter

from app.api.v1 import auth, health, settings, vocabularies

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(settings.router)
router.include_router(vocabularies.router)
