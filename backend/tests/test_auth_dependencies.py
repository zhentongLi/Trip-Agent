"""
认证依赖工厂单元测试

测试 dependencies.py 中 get_current_user_id / get_optional_user_id 的行为，
直接调用依赖函数，不需要启动 HTTP 服务器。
"""
import os
import pytest

# 确保测试时存在 JWT_SECRET_KEY，不依赖 .env
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("AMAP_API_KEY", "dummy")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("LLM_BASE_URL", "http://dummy")
os.environ.setdefault("LLM_MODEL_ID", "dummy")

from app.dependencies import get_current_user_id, get_optional_user_id
from app.errors.types import AuthenticationError
from app.services.auth_service import create_access_token


def _make_token(user_id: int = 42, username: str = "testuser") -> str:
    return create_access_token(user_id, username)


def _bearer(token: str) -> str:
    return f"Bearer {token}"


# ─── get_current_user_id ──────────────────────────────────────────────────


def test_get_current_user_id_no_header_raises_401():
    with pytest.raises(AuthenticationError) as exc_info:
        get_current_user_id(authorization=None)
    assert exc_info.value.status_code == 401


def test_get_current_user_id_invalid_token_raises_401():
    with pytest.raises(AuthenticationError) as exc_info:
        get_current_user_id(authorization="Bearer invalid.token.here")
    assert exc_info.value.status_code == 401


def test_get_current_user_id_malformed_header_raises_401():
    """不是 Bearer 格式的 Authorization 头应视为无 token"""
    with pytest.raises(AuthenticationError):
        get_current_user_id(authorization="Basic dXNlcjpwYXNz")


def test_get_current_user_id_valid_token_returns_id():
    token = _make_token(user_id=99)
    result = get_current_user_id(authorization=_bearer(token))
    assert result == 99


# ─── get_optional_user_id ────────────────────────────────────────────────


def test_get_optional_user_id_no_header_returns_none():
    result = get_optional_user_id(authorization=None)
    assert result is None


def test_get_optional_user_id_invalid_token_returns_none():
    result = get_optional_user_id(authorization="Bearer invalid.token.here")
    assert result is None


def test_get_optional_user_id_valid_token_returns_id():
    token = _make_token(user_id=7)
    result = get_optional_user_id(authorization=_bearer(token))
    assert result == 7
