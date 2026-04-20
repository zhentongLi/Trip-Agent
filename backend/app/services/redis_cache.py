"""Redis 缓存服务（带 TTLCache 本地降级）

与 TTLCache 暴露完全相同的公开接口（get/set/aget/aset），
使调用方无需感知底层实现。

Redis 不可用（连接失败、序列化异常等）时自动降级到 fallback TTLCache，
日志记录具体原因，不抛出异常。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from loguru import logger

from .cache_service import TTLCache


class RedisCache:
    """Redis 持久化缓存，支持多实例共享 + 进程重启数据保留。"""

    def __init__(
        self,
        redis_client: Any,
        namespace: str,
        ttl_seconds: int,
        fallback: TTLCache,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._ttl = ttl_seconds
        self._fallback = fallback

    def _full_key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    # ──────────────────────────────────────────
    # 异步接口（供 async 路由使用）
    # ──────────────────────────────────────────

    async def aget(self, key: str) -> Optional[Any]:
        """从 Redis 读取缓存，命中则反序列化返回；失败时查本地。"""
        try:
            raw = await self._redis.get(self._full_key(key))
            if raw is None:
                return self._fallback.get(key)
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"redis_fallback domain=trip_cache op=aget err={e}")
            return self._fallback.get(key)

    async def aset(self, key: str, value: Any) -> None:
        """序列化后写入 Redis（带 TTL）；失败时写本地。"""
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
            if self._ttl > 0:
                await self._redis.setex(self._full_key(key), self._ttl, raw)
            else:
                await self._redis.set(self._full_key(key), raw)
            # 同步写本地，便于同进程内的同步 .get() 调用命中
            self._fallback.set(key, value)
        except Exception as e:
            logger.warning(f"redis_fallback domain=trip_cache op=aset err={e}")
            self._fallback.set(key, value)

    # ──────────────────────────────────────────
    # 同步接口（向后兼容；仅查本地 fallback）
    # ──────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """同步读：仅查本地 fallback（不阻塞事件循环）。"""
        return self._fallback.get(key)

    def set(self, key: str, value: Any) -> None:
        """同步写：仅写本地 fallback。异步路径应使用 aset()。"""
        self._fallback.set(key, value)

    # ──────────────────────────────────────────
    # 工具方法（与 TTLCache 保持接口一致）
    # ──────────────────────────────────────────

    def delete(self, key: str) -> None:
        self._fallback.delete(key)

    def clear(self) -> None:
        self._fallback.clear()

    def size(self) -> int:
        return self._fallback.size()
