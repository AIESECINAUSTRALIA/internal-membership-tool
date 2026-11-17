"""FastAPI application entrypoint.

Configures CORS, Origin validation, and versioned API routes.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.router import api_router
from app.config import get_settings

app = FastAPI(title="AIESEC Australia — Membership Tool API")


@app.middleware("http")
async def validate_request_origin(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject non-GET requests without the exact configured Origin."""
    if request.method not in ("GET", "OPTIONS"):
        origin = request.headers.get("origin")
        expected_origin = get_settings().app_base_url

        if origin != expected_origin:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid request origin"},
            )

    return await call_next(request)


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
    return {"status": "ok"}
