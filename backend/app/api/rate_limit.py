"""全局限流器（避免与 main.py 循环导入）"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
