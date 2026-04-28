"""
行程分享服务（功能21：行程分享）

Redis 可用时：Hash 持久化，重启不丢失，多实例共享。
Redis 不可用时：降级为内存 KV（原行为），TTL 7天。

字段说明（Redis Hash / 本地 dict）：
  plan        - JSON 字符串（TripPlan）
  title       - 分享标题
  ts          - 创建时间戳（float）
  creator_id  - 创建者用户 ID（str(int) 或 ""，旧数据缺失则视为 None）
"""

import json
import secrets
import string
import time
from typing import Any, Dict, Optional

from loguru import logger


class ShareStore:
    """行程分享存储。Redis 可用时持久化；否则内存 KV（进程内，7天 TTL）。"""

    TTL_SECONDS = 7 * 24 * 3600  # 7 days

    def __init__(
        self,
        redis_client: Any = None,
        namespace: str = "trip_agent",
        ttl_seconds: int = TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._ttl = ttl_seconds
        self._local: Dict[str, Dict[str, Any]] = {}

    # ──────────────────────────────────────────
    # 异步接口（Redis 路径）
    # ──────────────────────────────────────────

    async def acreate(self, plan_data: dict, title: str = "", creator_id: Optional[int] = None) -> str:
        """存储行程，返回 8 位 share_id。creator_id 为 None 时表示匿名分享。"""
        share_id = self._generate_id()
        creator_str = str(creator_id) if creator_id is not None else ""
        if self._redis:
            try:
                key = self._redis_key(share_id)
                await self._redis.hset(key, mapping={
                    "plan": json.dumps(plan_data, ensure_ascii=False),
                    "title": title,
                    "ts": str(time.time()),
                    "creator_id": creator_str,
                })
                if self._ttl > 0:
                    await self._redis.expire(key, self._ttl)
                logger.info(f"📤 行程分享已创建(Redis): {share_id} creator={creator_id}")
                return share_id
            except Exception as e:
                logger.warning(f"redis_fallback domain=share op=acreate err={e}")
        # 本地降级
        self._evict_expired()
        self._local[share_id] = {
            "plan": plan_data,
            "title": title,
            "ts": time.time(),
            "creator_id": creator_id,
        }
        logger.info(f"📤 行程分享已创建(本地): {share_id} creator={creator_id} (共 {len(self._local)} 条)")
        return share_id

    async def aget(self, share_id: str) -> Optional[dict]:
        """获取分享行程，过期/不存在则返回 None。返回 dict 含 creator_id（可能为 None）。"""
        if self._redis:
            try:
                key = self._redis_key(share_id)
                raw = await self._redis.hgetall(key)
                if not raw:
                    return None
                raw_creator = raw.get("creator_id", "")
                return {
                    "plan": json.loads(raw["plan"]),
                    "title": raw.get("title", ""),
                    "ts": float(raw.get("ts", 0)),
                    "creator_id": int(raw_creator) if raw_creator else None,
                }
            except Exception as e:
                logger.warning(f"redis_fallback domain=share op=aget err={e}")
        # 本地降级
        item = self._local.get(share_id)
        if item is None:
            return None
        if time.time() - item["ts"] > self._ttl:
            self._local.pop(share_id, None)
            return None
        return item

    async def acheck_owner(self, share_id: str, user_id: int) -> bool:
        """检查 user_id 是否是 share_id 的创建者。
        - 记录不存在 → False
        - creator_id 为 None（匿名分享或旧数据）→ False（保守拒绝）
        - creator_id == user_id → True
        """
        record = await self.aget(share_id)
        if not record:
            return False
        return record.get("creator_id") == user_id

    async def adelete(self, share_id: str) -> bool:
        """删除分享链接，返回是否存在。"""
        if self._redis:
            try:
                deleted = await self._redis.delete(self._redis_key(share_id))
                return bool(deleted)
            except Exception as e:
                logger.warning(f"redis_fallback domain=share op=adelete err={e}")
        return self._local.pop(share_id, None) is not None

    # ──────────────────────────────────────────
    # 同步接口（向后兼容，仅操作本地）
    # ──────────────────────────────────────────

    def create(self, plan_data: dict, title: str = "", creator_id: Optional[int] = None) -> str:
        self._evict_expired()
        share_id = self._generate_id()
        self._local[share_id] = {
            "plan": plan_data,
            "title": title,
            "ts": time.time(),
            "creator_id": creator_id,
        }
        logger.info(f"📤 行程分享已创建: {share_id} (共 {len(self._local)} 条)")
        return share_id

    def get(self, share_id: str) -> Optional[dict]:
        item = self._local.get(share_id)
        if item is None:
            return None
        if time.time() - item["ts"] > self._ttl:
            del self._local[share_id]
            return None
        return item

    def delete(self, share_id: str) -> bool:
        return self._local.pop(share_id, None) is not None

    def size(self) -> int:
        return len(self._local)

    # ──────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────

    def _redis_key(self, share_id: str) -> str:
        return f"{self._ns}:share:{share_id}"

    def _generate_id(self) -> str:
        alphabet = string.ascii_letters + string.digits
        while True:
            sid = "".join(secrets.choice(alphabet) for _ in range(8))
            if sid not in self._local:
                return sid

    @property
    def _store(self) -> Dict[str, Dict[str, Any]]:
        """向后兼容别名，测试代码通过 store._store 直接访问内部字典。"""
        return self._local

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._local.items() if now - v["ts"] > self._ttl]
        for k in expired:
            del self._local[k]
        if expired:
            logger.debug(f"🗑️ 清理过期分享: {len(expired)} 条")


# 全局单例（无 Redis，测试/向后兼容用）
share_store = ShareStore()
