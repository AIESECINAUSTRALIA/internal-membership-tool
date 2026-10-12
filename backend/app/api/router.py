"""Every versioned API route, mounted under `/api/v1` by `app/main.py`.

Add a feature's router here: `api_router.include_router(people.router)`.
"""

from fastapi import APIRouter

from app.api.v1 import auth, members

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(members.router)
