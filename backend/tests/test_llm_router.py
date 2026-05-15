"""
测试：双 LLM 路由（reasoning + fast）

覆盖：
  - get_fast_llm() 未配置时回退为 get_llm() 单例（向后兼容）
  - get_fast_llm() 配置完整时返回独立实例
  - LLM_ROUTING_ENABLED=false 强制回退主 LLM
  - NodeFactory._plan_single_day_async 调用 fast_llm 而非 llm
  - MultiAgentTripPlanner 构造时正确传播 fast_llm；省略时回退 llm
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── get_llm / get_fast_llm 路由测试 ──────────────────────────────────────────

class TestLLMFactories:
    def setup_method(self):
        # 清空 lru_cache，确保各测试独立
        from app.dependencies import get_llm, get_fast_llm
        get_llm.cache_clear()
        get_fast_llm.cache_clear()

    def teardown_method(self):
        from app.dependencies import get_llm, get_fast_llm
        get_llm.cache_clear()
        get_fast_llm.cache_clear()

    def test_fast_llm_falls_back_to_main_when_not_configured(self, monkeypatch):
        """未配置 LLM_FAST_MODEL_ID 时，get_fast_llm 应返回 get_llm() 同一实例"""
        monkeypatch.delenv("LLM_FAST_MODEL_ID", raising=False)
        monkeypatch.delenv("LLM_FAST_API_KEY", raising=False)
        monkeypatch.delenv("LLM_FAST_BASE_URL", raising=False)
        # 清空 settings 缓存（重新读取环境变量）
        from app.config import Settings
        monkeypatch.setattr("app.config.settings", Settings())
        monkeypatch.setattr("app.config.get_settings", lambda: Settings())

        from app.dependencies import get_llm, get_fast_llm
        get_llm.cache_clear()
        get_fast_llm.cache_clear()

        main = get_llm()
        fast = get_fast_llm()
        # 必须是同一实例（is 比较，不只是相等）
        assert fast is main, "未配置 fast 模型时应复用主 LLM 实例"

    def test_routing_disabled_forces_fallback(self, monkeypatch):
        """LLM_ROUTING_ENABLED=false 时即使配置了 fast model 也回退主 LLM"""
        monkeypatch.setenv("LLM_FAST_MODEL_ID", "glm-flash")
        from app.config import Settings
        fake_settings = Settings(LLM_ROUTING_ENABLED=False, LLM_FAST_MODEL_ID="glm-flash")
        monkeypatch.setattr("app.config.settings", fake_settings)
        monkeypatch.setattr("app.config.get_settings", lambda: fake_settings)

        from app.dependencies import get_llm, get_fast_llm
        get_llm.cache_clear()
        get_fast_llm.cache_clear()

        main = get_llm()
        fast = get_fast_llm()
        assert fast is main, "路由开关关闭时必须回退主 LLM"


# ── NodeFactory 单日规划使用 fast_llm 测试 ─────────────────────────────────

def _make_factory_with_separate_llms():
    """创建 NodeFactory 实例，主/快速 LLM 用不同 mock 以便断言哪个被调用。"""
    from app.agents.nodes import NodeFactory

    main_llm = MagicMock(name="main_llm")
    fast_llm = MagicMock(name="fast_llm")

    factory = NodeFactory(
        attraction_agent=MagicMock(),
        weather_agent=MagicMock(),
        hotel_agent=MagicMock(),
        food_agent=MagicMock(),
        llm=main_llm,
        fast_llm=fast_llm,
        amap_client=MagicMock(),
        invoke_with_retry=AsyncMock(),
        is_retryable_llm_error=lambda e: False,
        build_planner_query=MagicMock(),
        create_fallback_plan=MagicMock(),
    )
    return factory, main_llm, fast_llm


class TestNodeFactoryFastLLMRouting:
    def test_fast_llm_defaults_to_main_when_omitted(self):
        """构造时省略 fast_llm，应自动回退为 llm（向后兼容旧调用）"""
        from app.agents.nodes import NodeFactory
        main_llm = MagicMock()
        factory = NodeFactory(
            attraction_agent=MagicMock(),
            weather_agent=MagicMock(),
            hotel_agent=MagicMock(),
            food_agent=MagicMock(),
            llm=main_llm,
            amap_client=MagicMock(),
            invoke_with_retry=AsyncMock(),
            is_retryable_llm_error=lambda e: False,
            build_planner_query=MagicMock(),
            create_fallback_plan=MagicMock(),
        )
        assert factory._fast_llm is main_llm

    @pytest.mark.asyncio
    async def test_single_day_async_uses_fast_llm(self):
        """_plan_single_day_async 必须调用 fast_llm.ainvoke，不能用 main llm"""
        from app.models.schemas import TripRequest

        factory, main_llm, fast_llm = _make_factory_with_separate_llms()

        # 模拟有效的 DayPlan JSON 响应
        day_json = json.dumps({
            "date": "2026-06-01",
            "day_index": 0,
            "description": "第1天",
            "transportation": "公共交通",
            "accommodation": "经济型酒店",
            "hotel": {"name": "测试酒店", "address": "北京", "location": {"longitude": 116.4, "latitude": 39.9},
                      "price_range": "200-400", "rating": "4.2", "distance": "1km",
                      "type": "经济型", "estimated_cost": 250},
            "attractions": [{"name": "故宫", "address": "北京东城区", "location": {"longitude": 116.3, "latitude": 39.9},
                             "visit_duration": 180, "description": "皇家宫殿", "category": "历史", "ticket_price": 60}],
            "meals": [
                {"type": "breakfast", "name": "早餐店", "address": "北京", "description": "包子", "estimated_cost": 25},
                {"type": "lunch",     "name": "午餐店", "address": "北京", "description": "炒菜", "estimated_cost": 80},
                {"type": "dinner",    "name": "晚餐店", "address": "北京", "description": "火锅", "estimated_cost": 100},
            ],
        }, ensure_ascii=False)

        # invoke_with_retry 会调用传入的 lambda；lambda 内部调用 fast_llm.ainvoke
        # 我们让 invoke_with_retry 实际触发 lambda 并返回模拟响应
        async def fake_invoke_with_retry(coro_factory, label):
            await coro_factory()  # 触发 lambda（这会调用 fast_llm.ainvoke）
            resp = MagicMock()
            resp.content = day_json
            return resp

        fast_llm.ainvoke = AsyncMock()
        main_llm.ainvoke = AsyncMock()
        factory._invoke_with_retry = fake_invoke_with_retry

        request = TripRequest(
            city="北京", start_date="2026-06-01", end_date="2026-06-01",
            travel_days=1, transportation="公共交通", accommodation="经济型酒店",
        )

        result = await factory._plan_single_day_async(
            "test_query", 0, "2026-06-01", request
        )

        # 断言：fast_llm.ainvoke 被调用，main_llm.ainvoke 未被调用
        assert fast_llm.ainvoke.called, "应通过 fast_llm 发起 LLM 调用"
        assert not main_llm.ainvoke.called, "主 LLM 不应被单日规划调用"
        assert result is not None
        assert result.day_index == 0


# ── MultiAgentTripPlanner 构造路由测试 ────────────────────────────────────

class TestTripPlannerWiring:
    def test_fast_llm_defaults_to_main(self):
        """构造时省略 fast_llm，self._fast_llm 应回退为 llm"""
        from app.agents.planner import MultiAgentTripPlanner

        main_llm = MagicMock()
        amap = MagicMock()
        planner = MultiAgentTripPlanner(llm=main_llm, amap_client=amap)
        assert planner._fast_llm is main_llm

    def test_fast_llm_propagated_to_node_factory(self):
        """构造时传入 fast_llm，NodeFactory 应收到同一实例"""
        from app.agents.planner import MultiAgentTripPlanner

        main_llm = MagicMock()
        fast_llm = MagicMock()
        amap = MagicMock()
        planner = MultiAgentTripPlanner(
            llm=main_llm, amap_client=amap, fast_llm=fast_llm
        )
        assert planner._fast_llm is fast_llm
        assert planner._node_factory._fast_llm is fast_llm
        assert planner._node_factory._llm is main_llm
