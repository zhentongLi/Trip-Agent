"""
测试：API 路由（集成测试）
涵盖 health / trip/share / trip/adjust 端点
使用 httpx.AsyncClient + ASGITransport（不依赖真实 LLM）
"""
import json
import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from app.api.main import app
from tests.conftest import SAMPLE_TRIP_PLAN


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ─── 健康检查 ───────────────────────────────────────────────────────────────

class TestHealthCheck:
    async def test_root_returns_running(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "version" in data

    async def test_docs_accessible(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200


# ─── 行程分享 (/api/trip/share) ─────────────────────────────────────────────

class TestShareRoutes:
    async def test_create_share_success(self, client):
        payload = {"plan": SAMPLE_TRIP_PLAN, "title": "北京三日游"}
        resp = await client.post("/api/trip/share", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["share_id"]) == 8
        assert "share_url" in data
        assert "expires_at" in data

    async def test_get_shared_trip_success(self, client):
        # 先创建分享
        payload = {"plan": SAMPLE_TRIP_PLAN}
        resp = await client.post("/api/trip/share", json=payload)
        share_id = resp.json()["share_id"]

        # 再获取
        resp2 = await client.get(f"/api/trip/share/{share_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["success"] is True
        assert data["data"]["city"] == "北京"

    async def test_get_nonexistent_share_returns_404(self, client):
        resp = await client.get("/api/trip/share/XXXXXXXX")
        assert resp.status_code == 404

    async def test_delete_share(self, client):
        payload = {"plan": SAMPLE_TRIP_PLAN}
        resp = await client.post("/api/trip/share", json=payload)
        share_id = resp.json()["share_id"]

        del_resp = await client.delete(f"/api/trip/share/{share_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        # 删完再 GET → 404
        get_resp = await client.get(f"/api/trip/share/{share_id}")
        assert get_resp.status_code == 404


# ─── AI 行程调整 (/api/trip/adjust) ─────────────────────────────────────────

class TestTripAdjust:
    async def test_adjust_rejects_empty_message(self, client):
        payload = {
            "trip_plan": SAMPLE_TRIP_PLAN,
            "user_message": "",
            "city": "北京",
        }
        resp = await client.post("/api/trip/adjust", json=payload)
        # 空 message 应被后端拒绝（422 Unprocessable Entity 或 400）
        assert resp.status_code in (400, 422)

    async def test_adjust_rejects_too_long_message(self, client):
        payload = {
            "trip_plan": SAMPLE_TRIP_PLAN,
            "user_message": "A" * 501,
            "city": "北京",
        }
        resp = await client.post("/api/trip/adjust", json=payload)
        assert resp.status_code in (400, 422)

    async def test_adjust_with_valid_payload_calls_agent(self, client, monkeypatch):
        """将 get_trip_planner_agent mock 掉，验证路由层调用链正常"""
        import app.api.routes.trip as trip_module
        from app.models.schemas import TripPlan

        adjusted_plan = {**SAMPLE_TRIP_PLAN}
        adjusted_plan["overall_suggestions"] = "已调整"

        class FakePlanner:
            async def adjust_trip(self, trip_plan, user_message, city=""):
                return TripPlan(**adjusted_plan)

        monkeypatch.setattr(trip_module, "get_trip_planner_agent", lambda: FakePlanner())

        payload = {
            "trip_plan": SAMPLE_TRIP_PLAN,
            "user_message": "把第一天景点换成颐和园",
            "city": "北京",
        }
        resp = await client.post("/api/trip/adjust", json=payload)
        # mock 正常，应返回 200
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
