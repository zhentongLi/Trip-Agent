"""
测试通用配置 & fixtures
"""
import copy
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.api.main import app
from app.dependencies import get_trip_planner, get_trip_cache, get_skill_router
from app.services.cache_service import TTLCache


# ---------- 公用测试数据 ----------

SAMPLE_TRIP_PLAN = {
    "city": "北京",
    "start_date": "2025-08-01",
    "end_date": "2025-08-03",
    "travel_days": 3,
    "transportation": "公共交通",
    "accommodation": "经济型酒店",
    "overall_suggestions": "建议提前订票",
    "days": [
        {
            "day_number": 1,
            "date": "2025-08-01",
            "theme": "历史文化",
            "attractions": [
                {
                    "name": "故宫博物院",
                    "address": "北京市东城区景山前街4号",
                    "location": {"longitude": 116.3972, "latitude": 39.9179},
                    "visit_duration": 180,
                    "description": "中国最大古代宫殿建筑群",
                    "ticket_price": 60,
                }
            ],
            "meals": [
                {"type": "breakfast", "name": "护国寺小吃", "address": "北京市西城区护国寺街", "price_per_person": 30},
                {"type": "lunch", "name": "全聚德烤鸭", "address": "北京市东城区前门大街", "price_per_person": 150},
                {"type": "dinner", "name": "簋街麻辣小龙虾", "address": "北京市东城区簋街", "price_per_person": 100},
            ],
            "hotel": {"name": "北京饭店", "address": "北京市东城区长安街33号", "price_per_night": 500},
        }
    ],
}


@pytest.fixture
def sample_trip():
    """返回一份可用的行程计划字典（深拷贝）"""
    return copy.deepcopy(SAMPLE_TRIP_PLAN)


@pytest_asyncio.fixture
async def async_client():
    """异步 TestClient（httpx），不注入任何 mock"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------- Mock 构建器（供需要 mock LLM 的测试使用） ----------

def make_fake_planner(adjusted_plan: dict | None = None):
    """构造一个简单的 FakePlanner，不调用真实 LLM。

    Args:
        adjusted_plan: adjust_trip 返回的行程字典；默认返回 SAMPLE_TRIP_PLAN
    """
    from app.models.schemas import TripPlan

    _plan = adjusted_plan or SAMPLE_TRIP_PLAN

    class FakePlanner:
        async def adjust_trip(self, trip_plan, user_message, city=""):
            return TripPlan(**_plan)

        async def plan_trip_stream(self, request, cache=None):
            yield {"type": "progress", "percent": 100, "message": "mock done"}
            yield {"type": "done", "data": _plan}

    return FakePlanner()


@pytest_asyncio.fixture
async def client_with_mock_planner(adjusted_plan=None):
    """注入 FakePlanner 的测试客户端（不调用真实 LLM）"""
    fake = make_fake_planner(adjusted_plan)
    app.dependency_overrides[get_trip_planner] = lambda: fake
    app.dependency_overrides[get_trip_cache] = lambda: TTLCache(ttl_seconds=60)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_trip_planner, None)
        app.dependency_overrides.pop(get_trip_cache, None)
