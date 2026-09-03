"""FastAPI application entrypoint — minimal starter.

Just enough to serve the API locally during development: a root greeting and a
liveness probe. Real configuration (Pydantic Settings), the database session,
routers, and auth arrive in the implementation phase — see the spec §8 and the
setup runbook §7 in
``docs/superpowers/specs/2026-09-02-project-skeleton-design.md``.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from the Membership Tool API"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. A database readiness check is added with app/db/session.py."""
    return {"status": "ok"}
