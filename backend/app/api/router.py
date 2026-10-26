"""Top-level API router mounting all versioned sub-routers."""

from fastapi import APIRouter

from app.api.v1 import lcs, members

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(members.router)
api_router.include_router(lcs.router)
