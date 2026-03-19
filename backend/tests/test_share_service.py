"""
测试：ShareStore（功能21 行程分享服务）
涵盖 create / get / delete / TTL 过期 / ID 唯一性
"""
import time
import pytest

from app.services.share_service import ShareStore


@pytest.fixture
def store():
    """每个用例使用独立的 ShareStore 实例，避免全局状态污染"""
    return ShareStore()


PLAN = {"city": "上海", "days": []}


class TestShareStoreCreate:
    def test_returns_8_char_id(self, store):
        sid = store.create(PLAN)
        assert len(sid) == 8

    def test_id_is_alphanumeric(self, store):
        sid = store.create(PLAN)
        assert sid.isalnum()

    def test_different_ids_for_consecutive_creates(self, store):
        ids = {store.create(PLAN) for _ in range(20)}
        # 20次创建得到 20 个不同的 ID（碰撞概率极低）
        assert len(ids) == 20

    def test_size_increments(self, store):
        assert store.size() == 0
        store.create(PLAN)
        assert store.size() == 1
        store.create(PLAN)
        assert store.size() == 2


class TestShareStoreGet:
    def test_get_existing_returns_item(self, store):
        sid = store.create(PLAN, title="上海行程")
        item = store.get(sid)
        assert item is not None
        assert item["plan"] == PLAN
        assert item["title"] == "上海行程"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("XXXXXXXX") is None

    def test_get_expired_returns_none(self, store):
        """手动将 ts 设置为过期时间点，验证惰性淘汰"""
        sid = store.create(PLAN)
        # 把时间戳往前推超过 TTL
        store._store[sid]["ts"] = time.time() - store.TTL_SECONDS - 1
        assert store.get(sid) is None
        # 过期条目应被删除
        assert store.size() == 0


class TestShareStoreDelete:
    def test_delete_existing_returns_true(self, store):
        sid = store.create(PLAN)
        assert store.delete(sid) is True
        assert store.get(sid) is None

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete("XXXXXXXX") is False

    def test_delete_reduces_size(self, store):
        sid = store.create(PLAN)
        assert store.size() == 1
        store.delete(sid)
        assert store.size() == 0


class TestShareStoreEviction:
    def test_evict_expired_cleans_on_create(self, store):
        """创建新条目时会触发 _evict_expired，过期条目应被清理"""
        sid = store.create(PLAN)
        store._store[sid]["ts"] = time.time() - store.TTL_SECONDS - 1

        # 再创建一条新的 → 触发 _evict_expired
        store.create(PLAN)
        assert store.size() == 1  # 过期条目已被清理，只剩新条目
