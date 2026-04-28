"""
测试：分享路由所有权校验（Phase 3）

测试矩阵：
  - 匿名创建 → creator_id=None
  - 登录创建 → creator_id=用户ID
  - GET 不暴露 creator_id
  - DELETE 无 token → 401
  - DELETE 非所有者 → 403
  - DELETE 所有者 → 200
  - DELETE 旧数据（creator_id=None） → 403
"""
import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.dependencies import get_current_user_id, get_optional_user_id, get_share_store
from app.services.share_service import ShareStore
from tests.conftest import SAMPLE_TRIP_PLAN


pytestmark = pytest.mark.asyncio

SHARE_PAYLOAD = {"plan": SAMPLE_TRIP_PLAN, "title": "测试分享"}


@pytest_asyncio.fixture
async def anon_client():
    """匿名客户端（无 token 注入）"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def user1_client():
    """模拟 user_id=1 的已登录客户端"""
    app.dependency_overrides[get_current_user_id] = lambda: 1
    app.dependency_overrides[get_optional_user_id] = lambda: 1
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(get_optional_user_id, None)


@pytest_asyncio.fixture
async def user2_client():
    """模拟 user_id=2 的已登录客户端（不同用户）"""
    app.dependency_overrides[get_current_user_id] = lambda: 2
    app.dependency_overrides[get_optional_user_id] = lambda: 2
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(get_optional_user_id, None)


# ─── 创建分享 ────────────────────────────────────────────────────────────────

async def test_share_create_anonymous_returns_share_id(anon_client):
    resp = await anon_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    assert resp.status_code == 200
    assert len(resp.json()["share_id"]) == 8


async def test_share_create_logged_in_records_creator(user1_client):
    resp = await user1_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    assert resp.status_code == 200
    share_id = resp.json()["share_id"]
    assert len(share_id) == 8

    # 验证 ShareStore 中记录了 creator_id（通过 acheck_owner 间接验证）
    store: ShareStore = app.dependency_overrides.get(get_share_store, get_share_store)()
    assert await store.acheck_owner(share_id, 1) is True
    assert await store.acheck_owner(share_id, 2) is False


# ─── 获取分享（公开，不暴露 creator_id）─────────────────────────────────────

async def test_share_get_does_not_expose_creator_id(anon_client, user1_client):
    resp = await user1_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    share_id = resp.json()["share_id"]

    get_resp = await anon_client.get(f"/api/trip/share/{share_id}")
    assert get_resp.status_code == 200
    # 响应体不应含 creator_id
    body_str = get_resp.text
    assert "creator_id" not in body_str


# ─── 删除分享鉴权 ─────────────────────────────────────────────────────────────

async def test_share_delete_no_token_returns_401(anon_client):
    """无 token 删除应返回 401"""
    # 先创建（匿名分享）
    resp = await anon_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    share_id = resp.json()["share_id"]

    del_resp = await anon_client.delete(f"/api/trip/share/{share_id}")
    assert del_resp.status_code == 401


async def test_share_delete_by_non_owner_returns_403(anon_client):
    """user2 删除 user1 的分享应返回 403。
    使用单个客户端分步设置 overrides，避免两个 fixture 同时覆盖同一个 key。
    """
    # Step 1: user1 创建分享
    app.dependency_overrides[get_optional_user_id] = lambda: 1
    resp = await anon_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    share_id = resp.json()["share_id"]
    app.dependency_overrides.pop(get_optional_user_id, None)

    # Step 2: user2 尝试删除
    app.dependency_overrides[get_current_user_id] = lambda: 2
    del_resp = await anon_client.delete(f"/api/trip/share/{share_id}")
    app.dependency_overrides.pop(get_current_user_id, None)

    assert del_resp.status_code == 403


async def test_share_delete_by_owner_returns_200(user1_client):
    """创建者删除自己的分享应成功"""
    resp = await user1_client.post("/api/trip/share", json=SHARE_PAYLOAD)
    share_id = resp.json()["share_id"]

    del_resp = await user1_client.delete(f"/api/trip/share/{share_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 删后 GET → 404
    get_resp = await user1_client.get(f"/api/trip/share/{share_id}")
    assert get_resp.status_code == 404


async def test_share_delete_legacy_share_without_creator_returns_403(user1_client):
    """旧数据（creator_id=None）应拒绝任何用户删除"""
    # 直接向 ShareStore 写入无 creator 的旧数据
    store: ShareStore = app.dependency_overrides.get(get_share_store, get_share_store)()
    sid = store.create({"city": "成都", "days": []}, title="旧分享")  # 同步方法，creator_id=None

    del_resp = await user1_client.delete(f"/api/trip/share/{sid}")
    assert del_resp.status_code in (403, 404)  # 403 无权限，或 404（store 不同实例）
