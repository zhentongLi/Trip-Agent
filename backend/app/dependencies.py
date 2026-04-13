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

from langchain_openai import ChatOpenAI

from .agents.planner import MultiAgentTripPlanner
from .config import Settings, get_settings
from .services.amap_rest_client import AmapRestClient
from .services.cache_service import TTLCache
from .services.circuit_breaker import CircuitBreaker
from .services.share_service import ShareStore
from .skills.router import SkillRouter

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
    """高德 REST 客户端（含熔断器，进程级单例）"""
    settings = get_settings()
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
    """行程 TTL 缓存（进程级单例，TTL=1小时）"""
    return TTLCache(ttl_seconds=1 * 3600)


@lru_cache()
def get_share_store() -> ShareStore:
    """行程分享存储（进程级单例）"""
    return ShareStore()


# ──────────────────────────────────────────
# RAG / Skill 服务
# ──────────────────────────────────────────


@lru_cache()
def get_skill_router() -> SkillRouter:
    """Skill 路由器（含 GuideQASkill，进程级单例）"""
    from .skills.guide_qa_skill import GuideQASkill
    from .skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry.register(GuideQASkill())
    return SkillRouter(registry)


def get_memory_service():
    """MemoryService 单例，支持 dependency_overrides 覆盖。"""
    from .services.memory_service import get_memory_service as _impl
    from .services.memory_service import MemoryService  # noqa: F401 — for type hints
    return _impl()
