"""
测试：持久化记忆注入规划（Feature A）

测试矩阵：
  - plan_trip_stream 无 session_id → user_profile_hint=None，规划正常
  - plan_trip_stream 有 session_id → async_build_context 被调用，hint 注入
  - MemoryService.async_build_context 抛异常 → 规划仍正常完成（不崩溃）
  - 规划成功后 async_record_turn 被调用一次
  - _build_planner_query 接收 user_profile_hint 并追加到 query 末尾
  - _build_planner_query 无 hint 时不追加偏好段落
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.planner import MultiAgentTripPlanner
from tests.conftest import SAMPLE_TRIP_PLAN


pytestmark = pytest.mark.asyncio

# ── 辅助构造 ──────────────────────────────────────────────────────────────────

def _make_fake_trip_plan():
    """构造最小化 TripPlan 对象"""
    from app.models.schemas import TripPlan
    return TripPlan(**SAMPLE_TRIP_PLAN)


def _make_request():
    from app.models.schemas import TripRequest
    return TripRequest(
        city="北京",
        start_date="2025-08-01",
        end_date="2025-08-03",
        travel_days=3,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=[],
    )


def _make_planner_with_memory(memory_service):
    """构造注入了 mock memory_service 的 MultiAgentTripPlanner（跳过 LLM 初始化）。"""
    planner = object.__new__(MultiAgentTripPlanner)
    planner._memory_service = memory_service
    return planner


def _patch_graph(planner, trip_plan):
    """将 planner._graph.astream 替换为返回 async generator 的普通函数。"""
    planner._graph = MagicMock()
    # 必须是普通函数（不是 AsyncMock），返回值是 async generator
    planner._graph.astream = lambda *args, **kwargs: _fake_graph_stream(trip_plan)


# ── 单元测试：_build_planner_query hint 注入 ─────────────────────────────────

class TestBuildPlannerQueryHint:
    def _minimal_planner(self):
        """构造足以调用 _build_planner_query 的 planner（不初始化 LLM/Agent）。"""
        p = object.__new__(MultiAgentTripPlanner)
        p._memory_service = None
        return p

    def test_no_hint_query_has_no_preference_section(self):
        p = self._minimal_planner()
        q = p._build_planner_query(
            _make_request(), "景点", "天气", "酒店", "美食",
            user_profile_hint=None
        )
        assert "用户历史偏好" not in q

    def test_with_hint_query_contains_preference_section(self):
        p = self._minimal_planner()
        hint = "预算: 中等 | 风格: 历史文化"
        q = p._build_planner_query(
            _make_request(), "景点", "天气", "酒店", "美食",
            user_profile_hint=hint
        )
        assert "用户历史偏好" in q
        assert hint in q

    def test_hint_appended_after_extra_requirements(self):
        p = self._minimal_planner()
        req = _make_request()
        req.free_text_input = "请多安排户外活动"
        hint = "旅行风格: 休闲"
        q = p._build_planner_query(
            req, "景点", "天气", "酒店", "美食",
            user_profile_hint=hint
        )
        # hint 段应在 free_text_input 之后
        assert q.index("额外要求") < q.index("用户历史偏好")


# ── 集成测试：plan_trip_stream 记忆读写 ───────────────────────────────────────

class TestPlanTripStreamMemory:
    async def test_no_session_id_skips_memory(self):
        """无 session_id 时不调用 MemoryService。"""
        mock_memory = AsyncMock()
        planner = _make_planner_with_memory(mock_memory)
        _patch_graph(planner, _make_fake_trip_plan())

        events = []
        async for ev in planner.plan_trip_stream(_make_request(), cache=None, session_id=None):
            events.append(ev)

        mock_memory.async_build_context.assert_not_called()
        mock_memory.async_record_turn.assert_not_called()

    async def test_with_session_id_calls_build_context(self):
        """有 session_id 时应调用 async_build_context。"""
        mock_memory = AsyncMock()
        mock_memory.async_build_context.return_value = "预算: 中等"
        planner = _make_planner_with_memory(mock_memory)
        _patch_graph(planner, _make_fake_trip_plan())

        async for _ in planner.plan_trip_stream(_make_request(), cache=None, session_id="user_1"):
            pass

        mock_memory.async_build_context.assert_awaited_once_with("user_1")

    async def test_with_session_id_calls_record_turn_after_done(self):
        """规划成功后应调用 async_record_turn 一次。"""
        mock_memory = AsyncMock()
        mock_memory.async_build_context.return_value = ""
        planner = _make_planner_with_memory(mock_memory)
        _patch_graph(planner, _make_fake_trip_plan())

        async for _ in planner.plan_trip_stream(_make_request(), cache=None, session_id="user_1"):
            pass

        mock_memory.async_record_turn.assert_awaited_once()
        call_args = mock_memory.async_record_turn.await_args
        # 第一个位置参数应是 session_id
        assert call_args.args[0] == "user_1"

    async def test_memory_build_context_exception_does_not_crash(self):
        """async_build_context 抛异常时规划仍应正常完成。"""
        mock_memory = AsyncMock()
        mock_memory.async_build_context.side_effect = RuntimeError("Redis 连接失败")
        planner = _make_planner_with_memory(mock_memory)
        _patch_graph(planner, _make_fake_trip_plan())

        done_events = []
        async for ev in planner.plan_trip_stream(_make_request(), cache=None, session_id="user_1"):
            if ev.get("type") == "done":
                done_events.append(ev)

        assert len(done_events) == 1, "规划应正常完成并产生 done 事件"

    async def test_memory_record_turn_exception_does_not_crash(self):
        """async_record_turn 抛异常时不应影响已发出的 done 事件。"""
        mock_memory = AsyncMock()
        mock_memory.async_build_context.return_value = ""
        mock_memory.async_record_turn.side_effect = RuntimeError("写入失败")
        planner = _make_planner_with_memory(mock_memory)
        _patch_graph(planner, _make_fake_trip_plan())

        done_events = []
        async for ev in planner.plan_trip_stream(_make_request(), cache=None, session_id="user_1"):
            if ev.get("type") == "done":
                done_events.append(ev)

        assert len(done_events) == 1


# ── 辅助：伪造 LangGraph astream ─────────────────────────────────────────────

async def _fake_graph_stream(trip_plan):
    """模拟 LangGraph graph.astream() 产生三个节点更新（async generator）。"""
    yield {"gather": {
        "attraction_response": "景点数据",
        "weather_response": "天气数据",
        "hotel_response": "酒店数据",
        "food_response": "餐饮数据",
    }}
    yield {"plan": {"trip_plan": trip_plan, "error": None}}
    yield {"postprocess": {"trip_plan": trip_plan, "error": None}}
