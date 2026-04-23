"""POI 推荐 Skill（景点/餐厅/酒店按需搜索）。"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from .base import RuntimeSkill

# 类别关键词映射：将用户意图映射到高德 POI 类型关键词
_CATEGORY_KEYWORDS: Dict[str, str] = {
    "景点": "旅游景点",
    "餐厅": "餐饮",
    "美食": "餐饮",
    "酒店": "酒店",
    "住宿": "酒店",
    "购物": "购物",
    "娱乐": "娱乐",
}


class POIRecommendSkill(RuntimeSkill):
    """封装高德 POI 搜索能力，返回结构化地点推荐列表。

    复用已有的 AmapRestClient.search_places_structured_async，
    避免另起 HTTP 客户端，并统一经过熔断器保护。

    构造参数:
        amap_client: AmapRestClient 实例（提供 search_places_structured_async 方法）。
    """

    name = "poi_recommend"
    description = "基于高德地图 POI 搜索，推荐景点、餐厅、酒店等地点"

    def __init__(self, amap_client: Any) -> None:
        """
        Args:
            amap_client: AmapRestClient 实例。
        """
        self._amap = amap_client

    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行 POI 推荐。

        payload 期望字段：
            city     (str): 目标城市（必填）。
            keywords (str): 搜索关键词，如"故宫"、"火锅"（必填）。
            category (str): 类别提示，如"景点"/"餐厅"/"酒店"（可选，辅助映射关键词）。
            limit    (int): 返回结果数量，默认 8，最大 20。
        """
        city = str(payload.get("city", "")).strip()
        if not city:
            raise ValueError("city 不能为空")

        keywords = str(payload.get("keywords", "")).strip()
        category = str(payload.get("category", "")).strip()

        # 若没有 keywords，使用 category 映射到默认搜索词
        if not keywords and category:
            keywords = _CATEGORY_KEYWORDS.get(category, category)
        if not keywords:
            raise ValueError("keywords 或 category 至少提供一个")

        limit = min(int(payload.get("limit", 8)), 20)

        logger.info(
            "🧩 Skill命中: {} | city={} | keywords={} | limit={}",
            self.name,
            city,
            keywords,
            limit,
        )

        pois = await self._amap.search_places_structured_async(keywords, city, limit)

        return {
            "city": city,
            "keywords": keywords,
            "total": len(pois),
            "places": pois,
            "skill_meta": {
                "skill_name": self.name,
                "skill_description": self.description,
                "category": category or "-",
            },
        }
