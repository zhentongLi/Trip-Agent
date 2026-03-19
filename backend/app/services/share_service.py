"""
行程分享服务（功能21：行程分享）
基于内存 KV 存储，支持 7 天时效的分享链接。
"""

import time
import secrets
import string
from typing import Dict, Optional, Any
from loguru import logger


class ShareStore:
    """简单的内存分享存储（TTL 7天）"""

    TTL_SECONDS = 7 * 24 * 3600  # 7 天

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def create(self, plan_data: dict, title: str = "") -> str:
        """存储行程，返回 8 位 share_id"""
        self._evict_expired()
        share_id = self._generate_id()
        self._store[share_id] = {
            "plan": plan_data,
            "title": title,
            "ts": time.time(),
        }
        logger.info(f"📤 行程分享已创建: {share_id} (共 {len(self._store)} 条)")
        return share_id

    def get(self, share_id: str) -> Optional[dict]:
        """获取分享行程，过期则返回 None"""
        item = self._store.get(share_id)
        if item is None:
            return None
        if time.time() - item["ts"] > self.TTL_SECONDS:
            del self._store[share_id]
            logger.info(f"🗑️ 分享 {share_id} 已过期，已删除")
            return None
        return item

    def delete(self, share_id: str) -> bool:
        return self._store.pop(share_id, None) is not None

    def size(self) -> int:
        return len(self._store)

    def _generate_id(self) -> str:
        """生成 8 位 URL 安全随机 ID"""
        alphabet = string.ascii_letters + string.digits
        while True:
            sid = "".join(secrets.choice(alphabet) for _ in range(8))
            if sid not in self._store:
                return sid

    def _evict_expired(self):
        """清理过期条目（惰性 + 主动定期）"""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v["ts"] > self.TTL_SECONDS]
        for k in expired:
            del self._store[k]
        if expired:
            logger.debug(f"🗑️ 清理过期分享: {len(expired)} 条")


# 全局单例
share_store = ShareStore()
