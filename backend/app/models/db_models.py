"""
数据库模型定义（功能18/23：用户账号 + 行程持久化）

使用 SQLModel (Pydantic + SQLAlchemy)，默认 SQLite 存储于 data/trip_planner.db。
"""
import json
from datetime import datetime
from typing import Optional, List

from sqlmodel import Field, SQLModel, create_engine, Session, select

# ──────────────────────────────────────────────────────────────────────────
# 数据库表模型
# ──────────────────────────────────────────────────────────────────────────

class User(SQLModel, table=True):
    """用户表"""
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, min_length=2, max_length=32)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)


class SavedTrip(SQLModel, table=True):
    """已保存行程表"""
    __tablename__ = "saved_trips"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    city: str
    title: str = Field(default="")
    plan_json: str          # JSON 序列化的 TripPlan
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────────────────────────────────
# API 请求/响应模型（不是数据库表，只是 Pydantic 模型）
# ──────────────────────────────────────────────────────────────────────────

class UserRegisterRequest(SQLModel):
    username: str = Field(min_length=2, max_length=32)
    email: str
    password: str = Field(min_length=6)


class UserLoginRequest(SQLModel):
    username: str
    password: str


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    user_id: int


class SavedTripOut(SQLModel):
    id: int
    city: str
    title: str
    created_at: datetime


class SavedTripDetail(SQLModel):
    id: int
    city: str
    title: str
    plan_json: str
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────────
# 数据库引擎 & 会话工厂
# ──────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path

_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{_DB_DIR / 'trip_planner.db'}"

_engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_tables():
    """创建所有数据库表（应用启动时调用）"""
    SQLModel.metadata.create_all(_engine)


def get_session():
    """FastAPI 依赖注入：获取数据库会话"""
    with Session(_engine) as session:
        yield session
