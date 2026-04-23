"""高德地图 REST API 客户端（封装熔断器 + 重试）

整合原 trip_planner_agent.py 中的 5 处内联 requests.get 调用：
  - search_places  ← _make_amap_tools._search_places / _enrich_opening_hours
  - get_weather    ← _make_amap_tools._get_weather
  - geocode        ← _fix_coordinates / _geocode_city_center
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import requests
from loguru import logger

from .circuit_breaker import CircuitBreaker

_AMAP_BASE = "https://restapi.amap.com"

# 熔断参数：连续 5 次失败后开路，30s 后尝试半开
_DEFAULT_BREAKER = CircuitBreaker(
    name="amap",
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=1,
)


class AmapRestClient:
    """封装高德 REST API，所有调用均经过熔断器保护"""

    def __init__(
        self,
        api_key: str,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 10.0,
        retry_count: int = 1,
        retry_delay: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._breaker = circuit_breaker or _DEFAULT_BREAKER
        self._timeout = timeout
        self._retry_count = retry_count
        self._retry_delay = retry_delay

    # ─────────────────────────────────────────────
    # 内部：带重试的原始 GET，经过熔断器
    # ─────────────────────────────────────────────

    def _get(self, path: str, params: dict) -> dict:
        """同步 GET，含 1 次重试，经熔断器保护"""
        params["key"] = self._api_key

        def _do_request() -> dict:
            last_err: Exception | None = None
            for attempt in range(self._retry_count + 1):
                try:
                    resp = requests.get(
                        f"{_AMAP_BASE}{path}",
                        params=params,
                        timeout=self._timeout,
                    )
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e:
                    last_err = e
                    if attempt < self._retry_count:
                        time.sleep(self._retry_delay)
            raise last_err  # type: ignore[misc]

        return self._breaker.call(_do_request)

    async def _get_async(self, path: str, params: dict) -> dict:
        """异步 GET（在线程池中运行同步请求，不阻塞事件循环）"""
        params_with_key = {**params, "key": self._api_key}

        async def _do_async() -> dict:
            return await asyncio.to_thread(self._get_sync_no_breaker, path, params_with_key)

        return await self._breaker.call_async(_do_async)

    def _get_sync_no_breaker(self, path: str, params: dict) -> dict:
        """不经熔断器的原始同步请求（供 _get_async 的线程池使用）"""
        last_err: Exception | None = None
        for attempt in range(self._retry_count + 1):
            try:
                resp = requests.get(
                    f"{_AMAP_BASE}{path}",
                    params=params,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < self._retry_count:
                    time.sleep(self._retry_delay)
        raise last_err  # type: ignore[misc]

    # ─────────────────────────────────────────────
    # 公开：搜索 POI（景点/酒店/餐厅）
    # ─────────────────────────────────────────────

    def search_places(self, keywords: str, city: str, limit: int = 10) -> str:
        """同步 POI 搜索，返回格式化文本（供 LangChain StructuredTool 使用）"""
        try:
            data = self._get(
                "/v3/place/text",
                {"keywords": keywords, "city": city, "output": "json"},
            )
            return self._format_pois(data, limit)
        except Exception as e:
            logger.warning(f"⚠️ search_places 失败 [{keywords}/{city}]: {e}")
            return f"查询失败: {e}"

    async def search_places_async(self, keywords: str, city: str, limit: int = 10) -> str:
        """异步 POI 搜索"""
        try:
            data = await self._get_async(
                "/v3/place/text",
                {"keywords": keywords, "city": city, "output": "json"},
            )
            return self._format_pois(data, limit)
        except Exception as e:
            logger.warning(f"⚠️ search_places_async 失败 [{keywords}/{city}]: {e}")
            return f"查询失败: {e}"

    @staticmethod
    def _format_pois(data: dict, limit: int = 10) -> str:
        if data.get("status") == "1" and data.get("pois"):
            pois = data["pois"][:limit]
            lines = []
            for poi in pois:
                biz = poi.get("biz_ext") or {}
                lines.append(
                    f"名称: {poi.get('name', '')} | "
                    f"地址: {poi.get('address', '')} | "
                    f"坐标: {poi.get('location', '')} | "
                    f"评分: {biz.get('rating', 'N/A')}"
                )
            return "\n".join(lines)
        return "未找到相关信息"

    # ─────────────────────────────────────────────
    # 公开：天气查询
    # ─────────────────────────────────────────────

    def get_weather(self, city: str) -> str:
        """同步天气查询，返回格式化文本"""
        try:
            data = self._get(
                "/v3/weather/weatherInfo",
                {"city": city, "extensions": "all", "output": "json"},
            )
            return self._format_weather(data)
        except Exception as e:
            logger.warning(f"⚠️ get_weather 失败 [{city}]: {e}")
            return f"天气查询失败: {e}"

    async def get_weather_async(self, city: str) -> str:
        """异步天气查询"""
        try:
            data = await self._get_async(
                "/v3/weather/weatherInfo",
                {"city": city, "extensions": "all", "output": "json"},
            )
            return self._format_weather(data)
        except Exception as e:
            logger.warning(f"⚠️ get_weather_async 失败 [{city}]: {e}")
            return f"天气查询失败: {e}"

    @staticmethod
    def _format_weather(data: dict) -> str:
        if data.get("status") == "1" and data.get("forecasts"):
            casts = data["forecasts"][0].get("casts", [])
            lines = []
            for c in casts:
                lines.append(
                    f"日期: {c.get('date')} | "
                    f"白天: {c.get('dayweather')} {c.get('daytemp')}℃ | "
                    f"夜间: {c.get('nightweather')} {c.get('nighttemp')}℃ | "
                    f"风向: {c.get('daywind')} {c.get('daypower')}级"
                )
            return "\n".join(lines) if lines else "暂无天气预报"
        return "天气查询失败（城市名可能不正确）"

    # ─────────────────────────────────────────────
    # 公开：地理编码
    # ─────────────────────────────────────────────

    def geocode(self, address: str, city: str = "") -> Optional[tuple[float, float]]:
        """同步地理编码，返回 (lng, lat) 或 None"""
        try:
            params: dict = {"address": address}
            if city:
                params["city"] = city
            data = self._get("/v3/geocode/geo", params)
            return self._parse_geocode(data, address)
        except Exception as e:
            logger.warning(f"⚠️ geocode 失败 [{address}]: {e}")
            return None

    async def geocode_async(
        self, address: str, city: str = ""
    ) -> Optional[tuple[float, float]]:
        """异步地理编码"""
        try:
            params: dict = {"address": address}
            if city:
                params["city"] = city
            data = await self._get_async("/v3/geocode/geo", params)
            return self._parse_geocode(data, address)
        except Exception as e:
            logger.warning(f"⚠️ geocode_async 失败 [{address}]: {e}")
            return None

    @staticmethod
    def _parse_geocode(data: dict, label: str) -> Optional[tuple[float, float]]:
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"]
            lng, lat = loc.split(",")
            logger.debug(f"🌏 geocode [{label}]: {lng},{lat}")
            return float(lng), float(lat)
        return None

    # ─────────────────────────────────────────────
    # 公开：获取景点开放时间（直接返回字符串）
    # ─────────────────────────────────────────────

    def get_opening_hours(self, name: str, city: str) -> Optional[str]:
        """同步获取 POI 开放时间，返回字符串或 None"""
        try:
            data = self._get(
                "/v3/place/text",
                {"keywords": name, "city": city, "output": "json"},
            )
            if data.get("status") == "1" and data.get("pois"):
                poi = data["pois"][0]
                biz = poi.get("biz_ext") or {}
                return (
                    biz.get("opentime")
                    or poi.get("business_area")
                    or None
                )
        except Exception as e:
            logger.debug(f"获取开放时间失败 [{name}]: {e}")
        return None

    async def get_opening_hours_async(self, name: str, city: str) -> Optional[str]:
        """异步获取 POI 开放时间，返回字符串或 None"""
        try:
            data = await self._get_async(
                "/v3/place/text",
                {"keywords": name, "city": city, "output": "json"},
            )
            if data.get("status") == "1" and data.get("pois"):
                poi = data["pois"][0]
                biz = poi.get("biz_ext") or {}
                return (
                    biz.get("opentime")
                    or poi.get("business_area")
                    or None
                )
        except Exception as e:
            logger.debug(f"异步获取开放时间失败 [{name}]: {e}")
        return None

    # ─────────────────────────────────────────────
    # 公开：结构化 POI 搜索（返回字典列表）
    # ─────────────────────────────────────────────

    async def search_places_structured_async(
        self, keywords: str, city: str, limit: int = 10
    ) -> list[dict]:
        """异步 POI 搜索，返回结构化字典列表（供 Skill 使用）。

        每个字典包含：id, name, type, address, location (dict), tel, rating。
        """
        try:
            data = await self._get_async(
                "/v3/place/text",
                {"keywords": keywords, "city": city, "output": "json"},
            )
            if data.get("status") == "1" and data.get("pois"):
                pois = data["pois"][:limit]
                result = []
                for poi in pois:
                    loc_str = poi.get("location", "0,0")
                    try:
                        lng, lat = loc_str.split(",")
                    except ValueError:
                        lng, lat = "0", "0"
                    biz = poi.get("biz_ext") or {}
                    result.append({
                        "id": poi.get("id", ""),
                        "name": poi.get("name", ""),
                        "type": poi.get("type", ""),
                        "address": poi.get("address", ""),
                        "location": {"longitude": float(lng), "latitude": float(lat)},
                        "tel": poi.get("tel") or None,
                        "rating": biz.get("rating") or None,
                    })
                return result
        except Exception as e:
            logger.warning(f"⚠️ search_places_structured_async 失败 [{keywords}/{city}]: {e}")
        return []
