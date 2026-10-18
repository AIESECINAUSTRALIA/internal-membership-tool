"""API v1 router — aggregates all feature routers."""

from fastapi import APIRouter

from app.api.v1.lcs import router as lcs_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(lcs_router)
