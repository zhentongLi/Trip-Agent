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
