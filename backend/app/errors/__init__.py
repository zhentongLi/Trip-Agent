"""错误处理模块"""

from .types import (
    AppError,
    ExternalServiceError,
    CircuitOpenError,
    PlanningError,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    RateLimitError,
)
from .schemas import ErrorResponse
from .handlers import register_error_handlers

__all__ = [
    "AppError",
    "ExternalServiceError",
    "CircuitOpenError",
    "PlanningError",
    "ValidationError",
    "NotFoundError",
    "AuthenticationError",
    "RateLimitError",
    "ErrorResponse",
    "register_error_handlers",
]
