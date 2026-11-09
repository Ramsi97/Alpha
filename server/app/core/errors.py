import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(422, "validation_error", str(exc.errors()))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # Plan section 18: structured JSON logs / Sentry for errors. This
        # handler is the last line of defense for anything not already an
        # ApiError or a validation error — without logging here, a real bug
        # (or someone probing for one) would be completely invisible: the
        # client gets a generic 500 and nothing is ever recorded anywhere.
        logger.exception("Unhandled exception", exc_info=exc)
        return _error_response(500, "internal_error", "Something went wrong.")
