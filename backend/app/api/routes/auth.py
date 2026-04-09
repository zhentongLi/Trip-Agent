"""
功能18：认证路由
POST /api/auth/register  — 注册
POST /api/auth/login     — 登录 → JWT
GET  /api/auth/me        — 当前用户信息（需 Bearer token）
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session

from ...api.rate_limit import limiter

from ...models.db_models import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    get_session,
)
from ...services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token,
    decode_token,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
)

router = APIRouter(prefix="/auth", tags=["用户认证"])
_bearer = HTTPBearer(auto_error=False)


def _current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_session),
):
    """依赖注入：从 Bearer token 解析当前用户 ID，失败时抛 401"""
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")
    return int(payload["sub"])


# ─── 注册 ─────────────────────────────────────────────────────────────────

@limiter.limit("5/minute")
@router.post("/register", response_model=TokenResponse, summary="用户注册")
def register(request: Request, body: UserRegisterRequest, session: Session = Depends(get_session)):
    # 检查用户名重复
    if get_user_by_username(session, body.username):
        raise HTTPException(status_code=400, detail="用户名已被占用")
    # 检查邮箱重复
    if get_user_by_email(session, body.email):
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = create_user(session, body.username, body.email, body.password)
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, username=user.username, user_id=user.id)


# ─── 登录 ─────────────────────────────────────────────────────────────────

@limiter.limit("10/minute")
@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(request: Request, body: UserLoginRequest, session: Session = Depends(get_session)):
    user = authenticate_user(session, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, username=user.username, user_id=user.id)


# ─── 当前用户 ─────────────────────────────────────────────────────────────

@router.get("/me", summary="获取当前用户信息")
def me(
    user_id: int = Depends(_current_user_id),
    session: Session = Depends(get_session),
):
    user = get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }
