"""FastAPI application entrypoint.

Serves a root greeting, a liveness probe, and the versioned API under
`/api/v1` (see `app/api/router.py`). Configuration comes from `app/config.py`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings

app = FastAPI(title="AIESEC Australia — Membership Tool API")

# Allow the frontend (the Vite dev server locally) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from the Membership Tool API"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. A database readiness check is added with app/db/session.py."""
    return {"status": "ok"}
