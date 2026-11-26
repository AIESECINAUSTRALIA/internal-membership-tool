"""Top-level API router mounting all versioned sub-routers."""

from fastapi import APIRouter

from app.api.v1 import (
    attributes,
    auth,
    data, 
    home,
    lcs,
    me,
    members,
    memberships,
    people,
    positions_functions,
    reference,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(members.router)
api_router.include_router(lcs.router)
api_router.include_router(positions_functions.router)
api_router.include_router(reference.router)
api_router.include_router(home.router)
api_router.include_router(data.router)
api_router.include_router(attributes.router)
api_router.include_router(me.router)
api_router.include_router(people.router)
api_router.include_router(memberships.router)
