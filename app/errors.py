"""One error shape for every endpoint: {"detail": "<message for people>", "code": "<ERROR_CODE>"}.

`detail` stays a string (the app shows it as is); `code` is for programs; request-validation errors
also list each bad field in `errors`. Before this, FastAPI's validation errors returned `detail` as a list.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Default code per HTTP status when the raiser gives none.
STATUS_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
    504: "TIMEOUT",
}
DEFAULT_MESSAGES = {
    400: "잘못된 요청입니다.",
    404: "없는 경로입니다.",
    405: "지원하지 않는 메서드입니다.",
    500: "서버 오류가 발생했습니다.",
}


class ApiError(HTTPException):
    """HTTPException with an explicit error code, e.g. ApiError(422, "...", code="INVALID_URL")."""

    def __init__(self, status_code, detail, code=None, headers=None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def error_body(status, detail, code=None, errors=None):
    body = {"detail": detail, "code": code or STATUS_CODES.get(status, "ERROR")}
    if errors:
        body["errors"] = errors
    return body


def _field(loc):
    # ("body", "qr_text") -> "qr_text"; ("query", "keyword") -> "keyword"
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return ".".join(parts) or "body"


def install_error_handlers(app: FastAPI):
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else DEFAULT_MESSAGES.get(exc.status_code, "요청을 처리하지 못했습니다.")
        return JSONResponse(error_body(exc.status_code, detail, getattr(exc, "code", None)),
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [{"field": _field(e.get("loc", ())), "message": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(error_body(422, "요청 형식이 올바르지 않습니다.", "VALIDATION_ERROR", errors), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, __: Exception):
        # Never echo internals (stack traces, upstream bodies, keys) to clients.
        return JSONResponse(error_body(500, DEFAULT_MESSAGES[500]), status_code=500)
