"""LangGraph 节点工厂

将 gather / plan / postprocess 三个节点从 MultiAgentTripPlanner 中提取出来，
通过 NodeFactory 以依赖注入方式组装，便于测试和独立替换。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from ..models.schemas import Location, TripPlan, TripRequest
from ..services.amap_rest_client import AmapRestClient
from .parsers import parse_trip_response
from .prompts import PLANNER_AGENT_PROMPT
from .state import PlannerState

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


class NodeFactory:
    """持有所有依赖，生成三个 LangGraph 节点方法。

    用法：
        factory = NodeFactory(attraction_agent, weather_agent, hotel_agent,
                              food_agent, llm, amap_client, invoke_with_retry,
                              is_retryable_llm_error, build_planner_query,
                              create_fallback_plan)
        workflow.add_node("gather",      factory.gather)
        workflow.add_node("plan",        factory.plan)
        workflow.add_node("postprocess", factory.postprocess)
    """

    def __init__(
        self,
        attraction_agent: Any,
        weather_agent: Any,
        hotel_agent: Any,
        food_agent: Any,
        llm: "ChatOpenAI",
        amap_client: AmapRestClient,
        invoke_with_retry: Callable,
        is_retryable_llm_error: Callable[[Exception], bool],
        build_planner_query: Callable,
        create_fallback_plan: Callable,
    ) -> None:
        self._attraction_agent = attraction_agent
        self._weather_agent = weather_agent
        self._hotel_agent = hotel_agent
        self._food_agent = food_agent
        self._llm = llm
        self._amap_client = amap_client
        self._invoke_with_retry = invoke_with_retry
        self._is_retryable_llm_error = is_retryable_llm_error
        self._build_planner_query = build_planner_query
        self._create_fallback_plan = create_fallback_plan

    # ──────────────────────────────────────────
    # 节点 1：gather（并行调用四个专项 Agent）
    # ──────────────────────────────────────────

    async def gather(self, state: PlannerState) -> dict:
        """并行调用四个专项 Agent，收集景点/天气/酒店/餐饮数据"""
        request: TripRequest = state["request"]
        cities: List[str] = state["cities"]
        primary_city = cities[0]

        food_pref = "、".join(request.preferences) if request.preferences else "特色"
        hotel_query = f"请搜索{primary_city}的{request.accommodation}酒店"
        food_query = f"请搜索{primary_city}的{food_pref}美食餐厅"

        attraction_queries: List[str] = []
        weather_queries: List[str] = []
        for city in cities[:3]:
            pref_kw = request.preferences[0] if request.preferences else "景点"
            attraction_queries.append(
                f"请搜索{city}的{pref_kw}相关景点，keywords={pref_kw}，city={city}"
            )
            weather_queries.append(f"请查询{city}的天气信息，city={city}")

        async def _invoke(agent, query: str, label: str) -> str:
            try:
                result = await self._invoke_with_retry(
                    lambda: agent.ainvoke({"messages": [HumanMessage(content=query)]}),
                    f"Agent[{label}]",
                )
                return result["messages"][-1].content
            except Exception as e:
                logger.warning(f"Agent [{label}] 调用异常: {e}")
                return f"暂无{label}数据"

        all_tasks = [
            *[
                _invoke(self._attraction_agent, q, f"{cities[i]}景点")
                for i, q in enumerate(attraction_queries)
            ],
            *[
                _invoke(self._weather_agent, q, f"{cities[i]}天气")
                for i, q in enumerate(weather_queries)
            ],
            _invoke(self._hotel_agent, hotel_query, "酒店"),
            _invoke(self._food_agent, food_query, "餐饮"),
        ]
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        n = len(cities[:3])
        attraction_results = all_results[:n]
        weather_results = all_results[n: 2 * n]
        hotel_result = all_results[2 * n]
        food_result = all_results[2 * n + 1]

        def _safe(r, label: str = "") -> str:
            if isinstance(r, Exception):
                logger.warning(f"并行任务异常 [{label}]: {r}")
                return f"暂无{label}数据"
            return str(r)

        if len(cities) > 1:
            attraction_response = "\n\n".join(
                f"【{cities[i]}景点信息】\n{_safe(r, f'{cities[i]}景点')}"
                for i, r in enumerate(attraction_results)
            )
            weather_response = "\n\n".join(
                f"【{cities[i]}天气信息】\n{_safe(r, f'{cities[i]}天气')}"
                for i, r in enumerate(weather_results)
            )
        else:
            attraction_response = _safe(attraction_results[0], "景点")
            weather_response = _safe(weather_results[0], "天气")

        logger.success(f"✅ gather 节点完成（{len(all_tasks)} 个并行任务）")
        return {
            "attraction_response": attraction_response,
            "weather_response": weather_response,
            "hotel_response": _safe(hotel_result, "酒店"),
            "food_response": _safe(food_result, "餐饮"),
        }

    # ──────────────────────────────────────────
    # 节点 2：plan（Planner LLM 整合 → JSON）
    # ──────────────────────────────────────────

    async def plan(self, state: PlannerState) -> dict:
        """调用 Planner LLM 整合信息，生成 JSON 行程"""
        request: TripRequest = state["request"]
        planner_query = self._build_planner_query(
            request,
            state["attraction_response"],
            state["weather_response"],
            state["hotel_response"],
            state["food_response"],
            cities=state["cities"],
        )
        try:
            response = await self._invoke_with_retry(
                lambda: self._llm.ainvoke([
                    SystemMessage(content=PLANNER_AGENT_PROMPT),
                    HumanMessage(content=planner_query),
                ]),
                "Planner",
            )
            trip_plan = parse_trip_response(response.content, request)
            if trip_plan is None:
                trip_plan = self._create_fallback_plan(request)
            logger.success("✅ plan 节点完成")
            return {"trip_plan": trip_plan, "error": None}
        except Exception as e:
            if self._is_retryable_llm_error(e):
                logger.warning(f"⚠️ plan 节点失败（上游临时不可用）: {e}")
            else:
                logger.error(f"❌ plan 节点失败: {e}")
            return {"trip_plan": None, "error": str(e)}

    # ──────────────────────────────────────────
    # 节点 3：postprocess（坐标修正 + 天气预警 + 开放时间）
    # ──────────────────────────────────────────

    def postprocess(self, state: PlannerState) -> dict:
        """修正坐标、添加天气预警、补充开放时间"""
        trip_plan: Optional[TripPlan] = state.get("trip_plan")
        if not trip_plan:
            return {"trip_plan": None, "error": state.get("error", "行程规划失败")}

        primary_city = state["primary_city"]
        self._fix_coordinates(trip_plan, primary_city)
        self._add_weather_warnings(trip_plan)
        self._enrich_opening_hours(trip_plan, primary_city)
        logger.success("✅ postprocess 节点完成")
        return {"trip_plan": trip_plan, "error": None}

    # ──────────────────────────────────────────
    # 后处理辅助方法
    # ──────────────────────────────────────────

    def _fix_coordinates(self, trip_plan: TripPlan, city: str) -> None:
        """通过高德地理编码 API 修正所有景点经纬度坐标"""
        for day in trip_plan.days:
            for attraction in day.attractions:
                if not attraction.address:
                    continue
                coords = self._amap_client.geocode(attraction.address, city)
                if coords:
                    lng, lat = coords
                    attraction.location = Location(longitude=lng, latitude=lat)
                    logger.debug(f"✅ 坐标修正: {attraction.name} → {lng},{lat}")

    def _geocode_city_center(self, city: str) -> tuple[float, float]:
        """获取城市中心坐标，失败时回退到北京"""
        _BEIJING = (116.4, 39.9)
        if not city:
            return _BEIJING
        coords = self._amap_client.geocode(city)
        if coords:
            return coords
        return _BEIJING

    def _add_weather_warnings(self, trip_plan: TripPlan) -> None:
        """检测极端天气并为每日天气信息添加预警标签"""
        extreme_keywords = [
            "暴雨", "大暴雨", "特大暴雨", "台风", "暴雪",
            "大雪", "冰雪", "沙尘暴", "冰暴", "龙卷风",
        ]
        HIGH_TEMP = 35
        LOW_TEMP = -10

        for weather in trip_plan.weather_info:
            warnings: List[str] = []

            combined = (weather.day_weather or "") + " " + (weather.night_weather or "")
            for kw in extreme_keywords:
                if kw in combined:
                    warnings.append(f"⚠️ {kw}预警")
                    break

            try:
                temp = int(weather.day_temp) if isinstance(weather.day_temp, str) else weather.day_temp
                if temp > HIGH_TEMP:
                    warnings.append(f"🌡️ 高温预警（{temp}°C）")
                elif temp < LOW_TEMP:
                    warnings.append(f"❄️ 严寒预警（{temp}°C）")
            except (ValueError, TypeError):
                pass

            m = re.search(r"(\d+)", str(weather.wind_power or ""))
            if m and int(m.group(1)) >= 7:
                warnings.append(f"💨 大风预警（{weather.wind_power}）")

            if warnings:
                weather.weather_warning = "；".join(warnings)
                logger.warning(f"🚨 {weather.date} 天气预警: {weather.weather_warning}")

    def _enrich_opening_hours(self, trip_plan: TripPlan, city: str) -> None:
        """通过高德 Place Search API 获取景点真实开放时间"""
        for day in trip_plan.days:
            for attraction in day.attractions:
                opentime = self._amap_client.get_opening_hours(attraction.name, city)
                if opentime:
                    attraction.opening_hours = opentime
                    logger.debug(f"🕐 {attraction.name} 开放时间: {opentime}")
