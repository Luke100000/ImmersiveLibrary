from fastapi import APIRouter

from immersive_library.routers import (
    auth,
    collection,
    content,
    deprecated,
    like,
    misc,
    render,
    report,
    tag,
    tools,
    user,
    viewer,
)

router = APIRouter()

router.include_router(deprecated.router)

router.include_router(auth.router)
router.include_router(collection.router)
router.include_router(content.router)
router.include_router(render.router)
router.include_router(like.router)
router.include_router(misc.router)
router.include_router(report.router)
router.include_router(tag.router)
router.include_router(tools.router)
router.include_router(user.router)
router.include_router(viewer.router)
