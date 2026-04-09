"""集中式异常处理器，注册到 FastAPI 应用"""

from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from .types import AppError
from .schemas import ErrorResponse


def register_error_handlers(app: FastAPI) -> None:
    """将所有异常处理器注册到 FastAPI 应用"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            f"AppError [{exc.error_code}] {request.method} {request.url.path}: {exc.message}"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(f"RequestValidationError {request.method} {request.url.path}: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error_code="REQUEST_VALIDATION_ERROR",
                message="请求参数校验失败",
                details={"errors": exc.errors()},
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled exception {request.method} {request.url.path}: {exc}\n"
            + traceback.format_exc()
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="服务器内部错误，请稍后重试",
            ).model_dump(),
        )
