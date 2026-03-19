"""
测试通用配置 & fixtures
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.main import app


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
    import copy
    return copy.deepcopy(SAMPLE_TRIP_PLAN)


@pytest.fixture
async def async_client():
    """异步 TestClient（httpx）"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
