"""应用异常层次结构"""

from __future__ import annotations


class AppError(Exception):
    """所有应用异常的基类"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class ExternalServiceError(AppError):
    """外部服务（AMap、LLM 等）调用失败"""

    def __init__(
        self,
        message: str,
        service_name: str,
        original_error: Exception | None = None,
        status_code: int = 502,
        error_code: str = "EXTERNAL_SERVICE_ERROR",
        details: dict | None = None,
    ) -> None:
        super().__init__(message, status_code, error_code, details)
        self.service_name = service_name
        self.original_error = original_error


class CircuitOpenError(ExternalServiceError):
    """熔断器已开路，拒绝调用外部服务"""

    def __init__(self, service_name: str) -> None:
        super().__init__(
            message=f"服务暂时不可用（熔断中）: {service_name}",
            service_name=service_name,
            status_code=503,
            error_code="CIRCUIT_OPEN",
        )


class PlanningError(AppError):
    """行程规划失败（LangGraph 节点错误）"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, status_code=500, error_code="PLANNING_FAILED", details=details)


class ValidationError(AppError):
    """业务层输入验证失败（区别于 Pydantic 的 RequestValidationError）"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, status_code=400, error_code="VALIDATION_ERROR", details=details)


class NotFoundError(AppError):
    """资源未找到（分享链接、保存的行程等）"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404, error_code="NOT_FOUND")


class AuthenticationError(AppError):
    """JWT 验证失败或未授权"""

    def __init__(self, message: str = "认证失败") -> None:
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_ERROR")


class RateLimitError(AppError):
    """自定义限流（用于流式接口内部限流检测）"""

    def __init__(self, message: str = "请求过于频繁，请稍后重试") -> None:
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_EXCEEDED")
