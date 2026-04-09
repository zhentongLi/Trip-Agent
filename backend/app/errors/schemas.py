"""统一错误响应 Schema"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """所有错误端点的统一响应信封"""

    success: bool = False
    error_code: str
    message: str
    details: dict | None = None
