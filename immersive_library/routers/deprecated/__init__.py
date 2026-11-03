from fastapi import APIRouter

from immersive_library.routers.deprecated import content, render, tag, user

router = APIRouter()
router.include_router(content.router)
router.include_router(user.router)
router.include_router(tag.router)
router.include_router(render.router)
