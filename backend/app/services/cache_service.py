"""简单的内存 TTL 缓存服务 (#16 响应缓存)

对相同城市+日期+偏好的请求进行缓存，默认 TTL 6 小时。
热门城市二次请求可以秒级返回，无需再次调用 LLM/Agent。
"""

import time
import hashlib
import json
from typing import Any, Optional
from loguru import logger


class TTLCache:
    """基于内存字典的 TTL 缓存，线程安全（GIL 保护）"""

    def __init__(self, ttl_seconds: int = 6 * 3600):
        self._store: dict[str, dict] = {}
        self._ttl = ttl_seconds
        logger.info(f"✅ 缓存服务初始化，TTL={ttl_seconds}s（{ttl_seconds//3600}小时）")

    # ---------- 公开接口 ----------

    def get(self, key: str) -> Optional[Any]:
        """读取缓存，若已过期则删除并返回 None"""
        item = self._store.get(key)
        if item is None:
            return None
        if time.time() - item["ts"] > self._ttl:
            del self._store[key]
            return None
        return item["data"]

    def set(self, key: str, value: Any) -> None:
        """写入缓存"""
        self._store[key] = {"data": value, "ts": time.time()}

    async def aget(self, key: str) -> Optional[Any]:
        """异步接口（供 RedisCache 降级时保持统一调用方式）"""
        return self.get(key)

    async def aset(self, key: str, value: Any) -> None:
        """异步接口（供 RedisCache 降级时保持统一调用方式）"""
        self.set(key, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
        logger.info("🗑️ 缓存已清空")

    def size(self) -> int:
        """返回有效缓存条目数（会先驱逐过期项）"""
        self._evict_expired()
        return len(self._store)

    def stats(self) -> dict:
        """返回缓存统计信息"""
        self._evict_expired()
        return {
            "size": len(self._store),
            "ttl_seconds": self._ttl,
            "keys": list(self._store.keys())
        }

    # ---------- 私有方法 ----------

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v["ts"] > self._ttl]
        for k in expired:
            del self._store[k]


def make_trip_cache_key(
    city: str,
    cities: Optional[list],
    start_date: str,
    end_date: str,
    preferences: list,
    accommodation: str,
    transportation: str,
    budget_limit: Optional[int],
) -> str:
    """根据请求关键参数生成稳定的缓存 key（MD5 前12位）"""
    raw = json.dumps(
        {
            "city": city,
            "cities": sorted(cities) if cities else None,
            "start_date": start_date,
            "end_date": end_date,
            "preferences": sorted(preferences),
            "accommodation": accommodation,
            "transportation": transportation,
            "budget_limit": budget_limit,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "trip:" + hashlib.md5(raw.encode()).hexdigest()[:12]


# 全局单例（TTL=6小时）
trip_cache = TTLCache(ttl_seconds=1 * 3600)
