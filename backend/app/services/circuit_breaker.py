"""通用熔断器实现

状态机：CLOSED → (failures >= threshold) → OPEN → (after recovery_timeout) → HALF_OPEN
         HALF_OPEN → (success) → CLOSED
         HALF_OPEN → (failure) → OPEN
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loguru import logger

from ..errors import CircuitOpenError

T = TypeVar("T")

# 熔断器状态常量
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    """线程安全的熔断器（支持同步和异步调用）"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = STATE_CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._get_state()

    def _get_state(self) -> str:
        """无锁版本，调用方需持有 _lock"""
        if self._state == STATE_OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = STATE_HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"🔌 熔断器 [{self.name}] 进入半开状态")
        return self._state

    def _before_call(self) -> None:
        """调用前检查，OPEN 时抛出 CircuitOpenError"""
        with self._lock:
            state = self._get_state()
            if state == STATE_OPEN:
                raise CircuitOpenError(self.name)
            if state == STATE_HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    raise CircuitOpenError(self.name)
                self._half_open_calls += 1

    def record_success(self) -> None:
        with self._lock:
            if self._state == STATE_HALF_OPEN:
                self._state = STATE_CLOSED
                self._failure_count = 0
                logger.success(f"✅ 熔断器 [{self.name}] 恢复关闭状态")
            elif self._state == STATE_CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == STATE_HALF_OPEN or self._failure_count >= self._failure_threshold:
                self._state = STATE_OPEN
                logger.warning(
                    f"⚡ 熔断器 [{self.name}] 开路（failures={self._failure_count}）"
                )

    def reset(self) -> None:
        with self._lock:
            self._state = STATE_CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._half_open_calls = 0
        logger.info(f"🔄 熔断器 [{self.name}] 已手动重置")

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """同步调用，自动记录成功/失败"""
        self._before_call()
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            self.record_failure()
            raise e

    async def call_async(
        self,
        coro_factory: Callable[..., Awaitable[T]],
        *args,
        **kwargs,
    ) -> T:
        """异步调用，自动记录成功/失败"""
        self._before_call()
        try:
            result = await coro_factory(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            self.record_failure()
            raise e


# ──────────────────────────────────────────────────────────────
# 分布式熔断器（Redis 后端，Lua 原子状态转换）
# 使用场景：多实例部署，各实例共享熔断状态，防止某一实例感知到故障
#           而其他实例继续向已故障的服务发起调用。
# ──────────────────────────────────────────────────────────────

# Lua：允许请求前检查状态；OPEN 超时则原子翻转为 HALF_OPEN
# 返回值: "allow" | "deny"
_LUA_BEFORE_CALL = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local recovery = tonumber(ARGV[2])
local half_max = tonumber(ARGV[3])

local state = redis.call('HGET', key, 'state') or 'closed'
if state == 'open' then
  local opened = tonumber(redis.call('HGET', key, 'opened_at') or '0')
  if now - opened >= recovery then
    redis.call('HSET', key, 'state', 'half_open', 'half_calls', '0')
    state = 'half_open'
  else
    return 'deny'
  end
end
if state == 'half_open' then
  local hc = tonumber(redis.call('HGET', key, 'half_calls') or '0')
  if hc >= half_max then
    return 'deny'
  end
  redis.call('HINCRBY', key, 'half_calls', 1)
end
return 'allow'
"""

# Lua：记录失败；达到阈值则翻转 OPEN
# 返回值: 当前 failures 计数
_LUA_RECORD_FAILURE = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local threshold = tonumber(ARGV[2])

local state = redis.call('HGET', key, 'state') or 'closed'
local failures = tonumber(redis.call('HINCRBY', key, 'failures', 1))
redis.call('HSET', key, 'last_failure_ts', tostring(now))

if state == 'half_open' or failures >= threshold then
  redis.call('HSET', key, 'state', 'open', 'opened_at', tostring(now))
end
return failures
"""

# Lua：记录成功（HALF_OPEN→CLOSED，清空计数）
_LUA_RECORD_SUCCESS = """
local key = KEYS[1]
local state = redis.call('HGET', key, 'state') or 'closed'
if state == 'half_open' then
  redis.call('HSET', key, 'state', 'closed', 'failures', '0', 'half_calls', '0')
elseif state == 'closed' then
  redis.call('HSET', key, 'failures', '0')
end
return redis.call('HGET', key, 'state')
"""


class RedisCircuitBreaker(CircuitBreaker):
    """Redis 后端分布式熔断器。

    多实例部署时各进程共享同一熔断状态，通过 Lua 脚本保证原子性。
    Redis 不可用时退化为父类（进程内状态）。

    通过 ``settings.circuit_breaker_redis_enabled=True`` 启用。
    """

    def __init__(
        self,
        name: str,
        redis_client: object,
        namespace: str = "trip_agent",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        super().__init__(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )
        self._redis = redis_client
        self._key = f"{namespace}:cb:{name}"
        self._before_call_script = self._redis.register_script(_LUA_BEFORE_CALL)
        self._failure_script = self._redis.register_script(_LUA_RECORD_FAILURE)
        self._success_script = self._redis.register_script(_LUA_RECORD_SUCCESS)

    def _before_call(self) -> None:
        try:
            result = self._before_call_script(
                keys=[self._key],
                args=[
                    str(time.time()),
                    str(self._recovery_timeout),
                    str(self._half_open_max_calls),
                ],
            )
            if result == "deny":
                raise CircuitOpenError(self.name)
        except CircuitOpenError:
            raise
        except Exception as e:
            logger.warning(f"RedisCircuitBreaker._before_call Redis 错误，降级本地: {e}")
            super()._before_call()

    def record_success(self) -> None:
        try:
            result = self._success_script(keys=[self._key], args=[])
            if result == "closed":
                logger.success(f"✅ 熔断器(Redis) [{self.name}] 恢复关闭状态")
        except Exception as e:
            logger.warning(f"RedisCircuitBreaker.record_success Redis 错误，降级本地: {e}")
            super().record_success()

    def record_failure(self) -> None:
        try:
            failures = self._failure_script(
                keys=[self._key],
                args=[str(time.time()), str(self._failure_threshold)],
            )
            logger.warning(
                f"⚡ 熔断器(Redis) [{self.name}] 记录失败 failures={failures}"
            )
        except Exception as e:
            logger.warning(f"RedisCircuitBreaker.record_failure Redis 错误，降级本地: {e}")
            super().record_failure()
