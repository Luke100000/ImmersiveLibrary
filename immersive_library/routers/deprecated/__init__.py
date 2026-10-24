from fastapi import APIRouter

from immersive_library.routers.deprecated import content, user

router = APIRouter()
router.include_router(content.router)
router.include_router(user.router)
