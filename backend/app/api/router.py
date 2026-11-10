"""Top-level API router mounting all versioned sub-routers."""

from fastapi import APIRouter

from app.api.v1 import auth, home, lcs, members, reference

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(members.router)
api_router.include_router(lcs.router)
api_router.include_router(reference.router)
api_router.include_router(home.router)
