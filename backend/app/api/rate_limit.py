"""全局限流器（避免与 main.py 循环导入）

REDIS_URL 配置时使用 Redis 存储后端，支持多实例共享限流计数。
未配置时降级为进程内存存储（单实例行为与原版一致）。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import get_settings

_settings = get_settings()
_storage_uri = _settings.redis_url if (not _settings.redis_disable and _settings.redis_url) else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
    strategy="fixed-window",
)
