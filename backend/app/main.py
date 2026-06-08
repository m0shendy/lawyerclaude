"""FastAPI application entrypoint for the Lawyer Office AI Engine.

Run with: ``uvicorn app.main:app`` (CWD = ``backend/``).

All error responses use the envelope ``{"error": {"code": str, "message": str}}``
(see docs/IMPLEMENTATION_CONVENTIONS.md).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.db import close_pool
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

# Map common HTTP status codes to stable lower_snake error codes.
_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Lawyer Office AI Engine", lifespan=lifespan)

    # CORS — origins from settings (env CORS_ORIGINS, comma-separated).
    origins = [
        origin.strip()
        for origin in get_settings().cors_origins.split(",")
        if origin.strip()
    ] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "validation_error", str(exc.errors()))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(500, "internal_error", "Internal server error")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Router includes — paths follow contracts/rest-api.md (no /api/v1 prefix).
    # ------------------------------------------------------------------
    from app.api import (
        ai_doc,
        ai_outputs,
        analytics,
        appointments,
        assignments,
        assistant,
        audit,
        auth,
        billing,
        calendar,
        cases,
        contacts,
        correspondence,
        deadlines,
        dms,
        documents,
        hearings,
        portal,
        references,
        reports,
        settings,
        tasks,
        templates,
        users,
    )

    # Core
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(cases.router)
    app.include_router(assignments.router)
    app.include_router(documents.router)
    app.include_router(ai_outputs.router)
    app.include_router(deadlines.router)
    app.include_router(tasks.router)
    app.include_router(reports.router)
    app.include_router(assistant.router)
    app.include_router(references.router)
    app.include_router(settings.router)
    app.include_router(audit.router)

    # Expansion modules (Phase 14–21)
    app.include_router(contacts.router,      tags=["contacts"])
    app.include_router(billing.router,       tags=["billing"])
    app.include_router(hearings.router,      tags=["hearings"])
    app.include_router(templates.router,     tags=["templates"])
    app.include_router(correspondence.router, tags=["correspondence"])
    app.include_router(analytics.router,     tags=["analytics"])
    app.include_router(portal.router)  # prefix="/portal" set in router

    # Spec 002 gap modules (DMS, appointments, calendar, AI doc features)
    app.include_router(dms.router,           tags=["dms"])
    app.include_router(appointments.router,  tags=["appointments"])
    app.include_router(calendar.router,      tags=["calendar"])
    app.include_router(ai_doc.router,        tags=["ai-doc"])

    return app


app = create_app()
