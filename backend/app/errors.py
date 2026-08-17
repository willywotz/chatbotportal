"""Standard error envelope: {"error": {"code", "message", "retryable", ...}}."""
from enum import StrEnum

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal"
    AGENCY_UNAVAILABLE = "agency_unavailable"
    AGENCY_TIMEOUT = "agency_timeout"


_STATUS_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL,
    502: ErrorCode.AGENCY_UNAVAILABLE,
    504: ErrorCode.AGENCY_TIMEOUT,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400,
                 retryable: bool = False, upstream_status: int | None = None):
        self.code, self.message = code, message
        self.status, self.retryable, self.upstream_status = status, retryable, upstream_status


def _envelope(code: str, message: str, retryable: bool = False, upstream_status: int | None = None) -> dict:
    err: dict = {"code": code, "message": message, "retryable": retryable}
    if upstream_status is not None:
        err["upstream_status"] = upstream_status
    return {"error": err}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status,
            content=_envelope(exc.code, exc.message, exc.retryable, exc.upstream_status),
        )

    async def _http_error(_req: Request, exc):
        code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), retryable=exc.status_code == 429),
            headers=getattr(exc, "headers", None),
        )

    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

    from app.services.responses.errors import register_responses_error_handler

    register_responses_error_handler(app)
