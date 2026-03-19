"""
功能18/23：用户认证服务
- 密码散列：passlib + bcrypt
- JWT：python-jose（HS256，默认 30 天有效期，供开发测试便利）
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import pbkdf2_sha256
from sqlmodel import Session, select
from loguru import logger

from ..models.db_models import User

# ── 密码哈希 ──────────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    try:
        return _pwd_context.hash(password)
    except Exception as e:
        # 兼容部分环境下 passlib+bcrypt 版本组合导致的哈希异常。
        logger.warning(f"bcrypt 哈希异常，回退到 pbkdf2_sha256: {e}")
        return pbkdf2_sha256.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.warning(f"bcrypt 校验异常，尝试 pbkdf2_sha256 校验: {e}")
        try:
            return pbkdf2_sha256.verify(plain, hashed)
        except Exception:
            return False


# ── JWT 配置 ───────────────────────────────────────────────────────────────
# 生产环境应从环境变量读取，这里提供合理默认值
_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))


def create_access_token(user_id: int, username: str) -> str:
    """生成 JWT access token"""
    expire = datetime.utcnow() + timedelta(days=_ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT，返回 payload 或 None（过期/无效）"""
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None


# ── 用户 CRUD ──────────────────────────────────────────────────────────────

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    return session.exec(select(User).where(User.username == username)).first()


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email)).first()


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def create_user(session: Session, username: str, email: str, password: str) -> User:
    """注册新用户，返回创建的 User 对象"""
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """校验用户名和密码，成功返回 User，失败返回 None"""
    user = get_user_by_username(session, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
