"""FastAPI 依赖注入提供者

所有服务实例通过此模块的 Depends() 工厂获取，
消除路由层中的全局单例调用，支持测试时的 dependency_overrides 替换。

用法（路由层）：
    from ..dependencies import get_trip_planner, get_trip_cache

    @router.post("/plan/stream")
    async def plan_trip_stream(
        request: Request,
        body: TripRequest,
        agent: MultiAgentTripPlanner = Depends(get_trip_planner),
        cache: TTLCache = Depends(get_trip_cache),
    ): ...

用法（测试层）：
    app.dependency_overrides[get_trip_planner] = lambda: mock_planner
    app.dependency_overrides[get_trip_cache]   = lambda: TTLCache(ttl_seconds=1)
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI
from loguru import logger

from .agents.planner import MultiAgentTripPlanner
from .config import Settings, get_settings
from .services.amap_rest_client import AmapRestClient
from .services.cache_service import TTLCache
from .services.circuit_breaker import CircuitBreaker, RedisCircuitBreaker
from .services.share_service import ShareStore
from .skills.router import SkillRouter

try:
    from redis import Redis
except ImportError:
    Redis = None  # type: ignore[assignment,misc]

try:
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio import ConnectionPool as AsyncConnectionPool
except ImportError:
    AsyncRedis = None  # type: ignore[assignment,misc]
    AsyncConnectionPool = None  # type: ignore[assignment]

# ──────────────────────────────────────────
# Redis 客户端工厂（进程级单例，连接失败自动降级）
# ──────────────────────────────────────────


@lru_cache()
def get_sync_redis() -> Optional["Redis"]:
    """同步 Redis 客户端（进程级单例）。Redis 不可用时返回 None。"""
    settings = get_settings()
    if settings.redis_disable or not settings.redis_url:
        return None
    if Redis is None:
        logger.warning("redis 包未安装，同步 Redis 客户端不可用")
        return None
    try:
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        client.ping()
        logger.info(f"✅ 同步 Redis 已连接 | url={settings.redis_url[:20]}...")
        return client
    except Exception as e:
        logger.warning(f"同步 Redis 连接失败，降级为本地存储: {e}")
        return None


@lru_cache()
def get_async_redis() -> Optional["AsyncRedis"]:
    """异步 Redis 客户端（进程级单例）。Redis 不可用时返回 None。

    注意：工厂本身是同步的（lru_cache 要求），连接在首次 await 时建立。
    """
    settings = get_settings()
    if settings.redis_disable or not settings.redis_url:
        return None
    if AsyncRedis is None:
        logger.warning("redis.asyncio 包未安装，异步 Redis 客户端不可用")
        return None
    try:
        pool = AsyncConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
            max_connections=int(os.getenv("MEMORY_REDIS_MAX_CONNECTIONS", "20")),
        )
        client = AsyncRedis(connection_pool=pool)
        logger.info(f"✅ 异步 Redis 已配置 | url={settings.redis_url[:20]}...")
        return client
    except Exception as e:
        logger.warning(f"异步 Redis 初始化失败，降级为本地存储: {e}")
        return None


# ──────────────────────────────────────────
# 底层基础设施
# ──────────────────────────────────────────


@lru_cache()
def get_llm() -> ChatOpenAI:
    """LLM 客户端（进程级单例）"""
    settings = get_settings()
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or settings.openai_api_key
    )
    base_url = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or settings.openai_base_url
    )
    model = (
        os.environ.get("LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or settings.openai_model
    )
    from loguru import logger
    logger.success(f"✅ LLM 初始化 | model={model} | base_url={base_url}")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url)


@lru_cache()
def get_amap_client() -> AmapRestClient:
    """高德 REST 客户端（含熔断器，进程级单例）。

    CIRCUIT_BREAKER_REDIS_ENABLED=true 且 Redis 可用时使用分布式熔断器；
    否则使用进程内熔断器（默认行为）。
    """
    settings = get_settings()
    sync_redis = get_sync_redis()
    if settings.circuit_breaker_redis_enabled and sync_redis is not None:
        breaker = RedisCircuitBreaker(
            name="amap",
            redis_client=sync_redis,
            namespace=settings.redis_namespace,
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=1,
        )
    else:
        breaker = CircuitBreaker(
            name="amap",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=1,
        )
    return AmapRestClient(api_key=settings.amap_api_key, circuit_breaker=breaker)


# ──────────────────────────────────────────
# 核心服务
# ──────────────────────────────────────────


@lru_cache()
def get_trip_planner() -> MultiAgentTripPlanner:
    """多智能体行程规划器（进程级单例）"""
    return MultiAgentTripPlanner(
        llm=get_llm(),
        amap_client=get_amap_client(),
    )


@lru_cache()
def get_trip_cache() -> TTLCache:
    """行程缓存（进程级单例）。Redis 可用时返回 RedisCache，否则返回 TTLCache。

    两者接口完全一致（get/set/aget/aset），调用方无需感知实现。
    """
    settings = get_settings()
    fallback = TTLCache(ttl_seconds=settings.trip_cache_ttl_seconds)
    async_redis = get_async_redis()
    if async_redis is not None:
        from .services.redis_cache import RedisCache
        return RedisCache(  # type: ignore[return-value]
            redis_client=async_redis,
            namespace=settings.redis_namespace,
            ttl_seconds=settings.trip_cache_ttl_seconds,
            fallback=fallback,
        )
    return fallback


@lru_cache()
def get_share_store() -> ShareStore:
    """行程分享存储（进程级单例）。Redis 可用时持久化到 Redis；否则内存存储。"""
    settings = get_settings()
    async_redis = get_async_redis()
    return ShareStore(
        redis_client=async_redis,
        namespace=settings.redis_namespace,
        ttl_seconds=settings.share_ttl_seconds,
    )


# ──────────────────────────────────────────
# RAG / Skill 服务
# ──────────────────────────────────────────


@lru_cache()
def get_skill_router() -> SkillRouter:
    """Skill 路由器（含全部已注册 Skill，进程级单例）。

    已注册 Skill（按 name 字母序）：
      - guide_qa      : GuideQASkill  — RAG 导游问答
      - poi_recommend : POIRecommendSkill — 高德 POI 推荐
      - trip_adjust   : TripAdjustSkill  — 自然语言行程调整
    """
    from .services.rag_service import get_guide_rag_service
    from .services.memory_service import get_memory_service as _get_memory
    from .skills.guide_qa_skill import GuideQASkill
    from .skills.poi_recommend_skill import POIRecommendSkill
    from .skills.trip_adjust_skill import TripAdjustSkill
    from .skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry.register(GuideQASkill(
        rag_service=get_guide_rag_service(),
        memory_service=_get_memory(),
    ))
    registry.register(POIRecommendSkill(amap_client=get_amap_client()))
    registry.register(TripAdjustSkill(planner=get_trip_planner()))
    return SkillRouter(registry)


def get_memory_service():
    """MemoryService 单例，支持 dependency_overrides 覆盖。"""
    from .services.memory_service import get_memory_service as _impl
    from .services.memory_service import MemoryService  # noqa: F401 — for type hints
    return _impl()
