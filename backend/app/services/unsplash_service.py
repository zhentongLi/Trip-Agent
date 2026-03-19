"""图片服务（使用 Unsplash API）"""

import requests

from typing import List, Optional
from loguru import logger
from ..config import get_settings


class UnsplashService:
    """图片服务类（基于 Unsplash API）"""

    BASE_URL = "https://api.unsplash.com"

    def __init__(self):
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        if not self.access_key:
            logger.warning("⚠️  Unsplash Access Key 未配置，图片功能不可用")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Client-ID {self.access_key}"})

    def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """
        搜索图片

        Args:
            query: 搜索关键词
            per_page: 返回数量

        Returns:
            图片信息列表
        """
        if not self.access_key:
            return []
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/search/photos",
                params={"query": query, "per_page": per_page, "orientation": "landscape"},
                timeout=10
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [
                {
                    "id": item["id"],
                    "url": item["urls"]["regular"],
                    "thumb": item["urls"]["thumb"],
                    "description": item.get("description") or item.get("alt_description") or query,
                    "photographer": item["user"]["name"]
                }
                for item in results
            ]
        except Exception as e:
            logger.error(f"❌ Unsplash 搜索失败: {e}")
            return []

    def get_photo_url(self, query: str, city: str = "") -> Optional[str]:
        """
        获取单张图片 URL

        Args:
            query: 搜索关键词（景点名称）
            city: 所在城市，用于增强图片与目的地的匹配度

        Returns:
            图片 URL，失败时返回 None
        """
        if not self.access_key:
            return None
        # 过滤 fallback 占位名称（含"待规划"或"景点"的内部名），改用城市关键词搜图
        is_placeholder = "待规划" in query or ("景点" in query and len(query) < 10)
        if is_placeholder and city:
            search_query = city  # 直接用城市名搜索，避免无意义关键词
        else:
            # 去掉中文括号等特殊字符，避免 Unsplash 410
            import re as _re
            clean_query = _re.sub(r'[（）【】《》""''\(\)\[\]]', ' ', query).strip()
            search_query = f"{clean_query} {city}".strip() if city else clean_query

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/search/photos",
                params={"query": search_query, "per_page": 1, "orientation": "landscape"},
                timeout=10
            )
            # 410 Gone：该查询被 Unsplash 永久拒绝，改用城市名重试一次
            if resp.status_code == 410:
                if city and search_query != city:
                    logger.debug(f"Unsplash 410，用城市名重试: {city}")
                    resp = self.session.get(
                        f"{self.BASE_URL}/search/photos",
                        params={"query": city, "per_page": 1, "orientation": "landscape"},
                        timeout=10
                    )
                if resp.status_code != 200:
                    logger.debug(f"Unsplash 返回 {resp.status_code}，跳过: {search_query}")
                    return None
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                url = results[0]["urls"]["regular"]
                logger.debug(f"图片URL: {search_query} → {url}")
                return url
            logger.debug(f"图片搜索无结果: {search_query}")
            return None
        except Exception as e:
            logger.debug(f"获取Unsplash图片失败（已忽略）: {e}")
            return None


# 全局服务实例
_unsplash_service = None


def get_unsplash_service() -> UnsplashService:
    """获取图片服务实例(单例模式)"""
    global _unsplash_service

    if _unsplash_service is None:
        _unsplash_service = UnsplashService()

    return _unsplash_service

