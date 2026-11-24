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

# Methods that must never change data, so they don't need an Origin check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _normalise_origin(origin: str) -> str:
    """`https://Members.Example.org/` and `https://members.example.org` are the same
    origin. Compare them in one canonical form so a trailing slash or capital
    letter in an environment variable can't lock everyone out."""
    return origin.strip().rstrip("/").lower()


def allowed_origins() -> frozenset[str]:
    """Origins that may send state-changing requests.

    - `FRONTEND_ORIGIN` is where the browser app runs. Locally that's the Vite dev
      server (http://localhost:5173), a different origin from the API.
    - `APP_BASE_URL` is the public URL of the deployment. On GCP, Firebase Hosting
      serves the frontend and forwards `/api/**` to Cloud Run, so it's the same
      origin as the frontend there.
    """
    settings = get_settings()
    return frozenset(
        _normalise_origin(origin)
        for origin in (settings.frontend_origin, settings.app_base_url)
        if origin
    )


@app.middleware("http")
async def validate_request_origin(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """CSRF protection: reject state-changing requests from other websites.

    Why this is needed: sign-in uses a session *cookie*, and browsers attach
    cookies automatically, even when another website makes the request. A
    malicious page could otherwise make a signed-in member's browser POST to our
    API. Browsers always send an `Origin` header on cross-site POST/PATCH/DELETE,
    and a page can't fake it, so we only accept writes whose Origin is one of ours.
    A request with no Origin at all is rejected too.
    """
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")

        if origin is None or _normalise_origin(origin) not in allowed_origins():
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
