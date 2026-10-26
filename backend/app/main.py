"""FastAPI application entrypoint.

Creates the app, configures CORS for the local Vite dev server, and mounts the
versioned API routers from `app/api/router.py`. Endpoints themselves live under
`app/api/v1/`; this file stays thin.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router

app = FastAPI(title="AIESEC Australia — Membership Tool API")

# Allow the local Vite dev server to call the API during development.
# Replaced by a config-driven allowlist in app/config.py during implementation.
_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin],
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
    """Liveness probe."""
    return {"status": "ok"}
