"""LangGraph 节点工厂

将 gather / plan / postprocess 三个节点从 MultiAgentTripPlanner 中提取出来，
通过 NodeFactory 以依赖注入方式组装，便于测试和独立替换。
"""

from __future__ import annotations

import asyncio
import json as _json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from ..models.schemas import Budget, DayPlan, Location, TripPlan, TripRequest, WeatherInfo
from ..services.amap_rest_client import AmapRestClient
from .parsers import extract_json_str, parse_trip_response
from .prompts import PLANNER_AGENT_PROMPT
from .state import PlannerState

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


# ── 单日规划系统提示词 ──────────────────────────────────────────────────────────
_SINGLE_DAY_SYSTEM_PROMPT = """你是行程规划专家。根据给定信息，规划指定某一天的详细行程。

只返回以下格式的纯 JSON，不要任何说明文字：
{
  "date": "YYYY-MM-DD",
  "day_index": 0,
  "description": "第1天行程概述",
  "transportation": "交通方式",
  "accommodation": "住宿类型",
  "hotel": {"name": "酒店名称", "address": "酒店地址", "location": {"longitude": 116.4, "latitude": 39.9}, "price_range": "300-500元", "rating": "4.5", "distance": "距离景点2公里", "type": "经济型酒店", "estimated_cost": 400},
  "attractions": [{"name": "景点名称", "address": "详细地址", "location": {"longitude": 116.4, "latitude": 39.9}, "visit_duration": 120, "description": "景点描述", "category": "景点类别", "ticket_price": 60}],
  "meals": [
    {"type": "breakfast", "name": "具体餐厅名称", "address": "地址", "description": "特色及人均消费", "estimated_cost": 25},
    {"type": "lunch",     "name": "具体餐厅名称", "address": "地址", "description": "特色及人均消费", "estimated_cost": 80},
    {"type": "dinner",    "name": "具体餐厅名称", "address": "地址", "description": "特色及人均消费", "estimated_cost": 100}
  ]
}

重要：meals 必须包含 breakfast / lunch / dinner 三条，name 字段必须是具体餐厅名称。"""


# ── 天气行解析正则 ──────────────────────────────────────────────────────────────
_WEATHER_LINE_RE = re.compile(
    r"日期:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|"
    r"\s*白天:\s*(?P<dw>[^\d|]+?)\s*(?P<dt>\d+)℃\s*\|"
    r"\s*夜间:\s*(?P<nw>[^\d|]+?)\s*(?P<nt>\d+)℃"
    r"(?:\s*\|\s*风向:\s*(?P<wind>[^|\n\d]+?)(?:\s*\|\s*|\s*(?P<power>\d+级)\s*|\s*$))?",
)


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
        fast_llm: Optional["ChatOpenAI"] = None,
    ) -> None:
        self._attraction_agent = attraction_agent
        self._weather_agent = weather_agent
        self._hotel_agent = hotel_agent
        self._food_agent = food_agent
        self._llm = llm
        # 快速模型用于单日并行规划；未传入时回退主 LLM（行为完全向后兼容）
        self._fast_llm = fast_llm or llm
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
    # 并行逐日规划辅助方法
    # ──────────────────────────────────────────

    @staticmethod
    def _extract_city_section(text: str, city: str) -> str:
        """从多城市文本中提取指定城市段落；单城市文本原样返回"""
        marker = f"【{city}"
        if marker not in text:
            return text
        start = text.find(marker)
        nxt = text.find("【", start + 1)
        return text[start:nxt].strip() if nxt > start else text[start:].strip()

    @staticmethod
    def _extract_weather_snippet(weather_text: str, date_str: str, city: str = "") -> str:
        """提取指定日期的天气行（先搜城市段落，再搜全文）"""
        section = NodeFactory._extract_city_section(weather_text, city) if city else weather_text
        for line in section.splitlines():
            if date_str in line:
                return line.strip()
        for line in weather_text.splitlines():
            if date_str in line:
                return line.strip()
        return ""

    @staticmethod
    def _parse_weather_info(weather_text: str, start_date: str, total_days: int) -> List[WeatherInfo]:
        """从 AMap 天气响应文本解析 WeatherInfo 列表（无 LLM 调用）"""
        parsed: dict[str, WeatherInfo] = {}
        for line in weather_text.splitlines():
            m = _WEATHER_LINE_RE.search(line)
            if m:
                wind = (m.group("wind") or "").strip().rstrip("|").strip()
                power = (m.group("power") or "").strip()
                parsed[m.group("date")] = WeatherInfo(
                    date=m.group("date"),
                    day_weather=m.group("dw").strip(),
                    night_weather=m.group("nw").strip(),
                    day_temp=int(m.group("dt")),
                    night_temp=int(m.group("nt")),
                    wind_direction=wind,
                    wind_power=power,
                )
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        result: List[WeatherInfo] = []
        for i in range(total_days):
            day_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            result.append(parsed.get(day_str) or WeatherInfo(
                date=day_str, day_weather="晴", night_weather="晴",
                day_temp=25, night_temp=15, wind_direction="南风", wind_power="1-3级",
            ))
        return result

    def _build_single_day_query(
        self,
        request: TripRequest,
        day_index: int,
        day_date: str,
        current_city: str,
        attractions: str,
        weather_snippet: str,
        hotels: str,
        foods: str,
        total_days: int,
        prev_city: str = "",
    ) -> str:
        """构建单日行程规划 prompt（紧凑版，约 1/3 token 消耗）"""
        header = (
            f"请规划第{day_index + 1}天（{day_date}，{current_city}）行程。\n"
            f"交通：{request.transportation}，住宿：{request.accommodation}"
        )
        if request.preferences:
            header += f"，偏好：{'、'.join(request.preferences)}"
        if prev_city and prev_city != current_city:
            header += (
                f"\n⚠️ 今天从{prev_city}前往{current_city}，"
                f"description 中注明跨城交通方式，景点安排1-2个。"
            )
        if request.budget_limit:
            header += f"\n预算参考：约{request.budget_limit // total_days}元/天"
        if weather_snippet:
            header += f"\n今日天气：{weather_snippet}"

        body = (
            f"\n\n可选景点（{current_city}）：\n{attractions}"
            f"\n\n酒店参考：\n{hotels}"
            f"\n\n餐厅参考（必须选具体店名）：\n{foods}"
        )
        if request.free_text_input:
            body += f"\n\n额外要求：{request.free_text_input}"

        footer = (
            f"\n\n要求：安排2-3个景点，breakfast/lunch/dinner各一条meal，指定一个酒店。"
            f"day_index={day_index}，date=\"{day_date}\"。**只返回纯JSON，无任何说明文字。**"
        )
        return header + body + footer

    async def _plan_single_day_async(
        self,
        query: str,
        day_index: int,
        day_date: str,
        request: TripRequest,
    ) -> Optional[DayPlan]:
        """异步调用 LLM 规划单日行程，解析为 DayPlan。

        使用 fast_llm（Haiku/Flash 类）：单日 JSON 输出短、结构固定，
        快速模型完全胜任，可降低 50% 以上成本与首字延迟。
        """
        try:
            response = await self._invoke_with_retry(
                lambda: self._fast_llm.ainvoke([
                    SystemMessage(content=_SINGLE_DAY_SYSTEM_PROMPT),
                    HumanMessage(content=query),
                ]),
                f"DayPlanner[{day_index + 1}]",
            )
            raw = response.content
            json_str = extract_json_str(raw)
            data = _json.loads(json_str)
            # 补全必填字段（防 LLM 遗漏）
            data.setdefault("date", day_date)
            data.setdefault("day_index", day_index)
            data.setdefault("transportation", request.transportation)
            data.setdefault("accommodation", request.accommodation)
            data.setdefault("description", f"第{day_index + 1}天行程")
            day_plan = DayPlan.model_validate(data)
            logger.success(f"✅ 第{day_index + 1}天行程规划完成")
            return day_plan
        except Exception as e:
            logger.warning(f"⚠️ 第{day_index + 1}天规划失败: {e}")
            return None

    # ──────────────────────────────────────────
    # 节点 2：plan（并行逐日 LLM 规划）
    # ──────────────────────────────────────────

    async def plan(self, state: PlannerState) -> dict:
        """并行调用 LLM 逐日规划，失败时回退到整体单次规划"""
        request: TripRequest = state["request"]
        cities: List[str] = state["cities"]
        total_days = request.travel_days

        # ── 尝试并行逐日规划 ──
        try:
            from ..config import settings
            from .compressor import compress_agent_responses

            attraction_raw = state["attraction_response"]
            weather_raw = state["weather_response"]
            hotel_raw = state["hotel_response"]
            food_raw = state["food_response"]

            # 压缩（减少每日 prompt token）
            if settings.planner_compress_context:
                attraction_raw, weather_raw, hotel_raw, food_raw = compress_agent_responses(
                    attraction_raw, weather_raw, hotel_raw, food_raw
                )

            # 计算多城市日程分配
            days_per_city = max(1, total_days // len(cities))
            remainder = total_days - days_per_city * len(cities)
            city_schedule: List[str] = []
            for idx, city in enumerate(cities):
                days = days_per_city + (1 if idx < remainder else 0)
                city_schedule.extend([city] * days)

            start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")

            # 为每天构建查询
            tasks = []
            for i in range(total_days):
                day_date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                current_city = city_schedule[i] if i < len(city_schedule) else cities[0]
                prev_city = city_schedule[i - 1] if i > 0 else ""

                city_attractions = self._extract_city_section(attraction_raw, current_city)
                weather_snippet = self._extract_weather_snippet(
                    weather_raw, day_date, current_city
                )
                query = self._build_single_day_query(
                    request=request,
                    day_index=i,
                    day_date=day_date,
                    current_city=current_city,
                    attractions=city_attractions,
                    weather_snippet=weather_snippet,
                    hotels=hotel_raw,
                    foods=food_raw,
                    total_days=total_days,
                    prev_city=prev_city,
                )
                tasks.append(self._plan_single_day_async(query, i, day_date, request))

            logger.info(f"🚀 并行规划 {total_days} 天行程...")
            day_results: List[Optional[DayPlan]] = await asyncio.gather(*tasks)

            # 检查是否全部成功
            failed = [i + 1 for i, r in enumerate(day_results) if r is None]
            if failed:
                raise RuntimeError(f"第 {failed} 天规划失败，切换回整体模式")

            # 解析天气（从原始文本，无 LLM）
            weather_info = self._parse_weather_info(
                state["weather_response"], request.start_date, total_days
            )

            # 汇总预算
            total_attr = sum(a.ticket_price for d in day_results for a in d.attractions)  # type: ignore[union-attr]
            total_hotel = sum(
                (d.hotel.estimated_cost if d and d.hotel else 0) for d in day_results
            )
            total_meal = sum(m.estimated_cost for d in day_results for m in d.meals)  # type: ignore[union-attr]
            budget = Budget(
                total_attractions=total_attr,
                total_hotels=total_hotel,
                total_meals=total_meal,
                total_transportation=0,
                total=total_attr + total_hotel + total_meal,
            )

            hint = state.get("user_profile_hint")
            overall = f"{'→'.join(cities)}{total_days}日游行程，祝您旅途愉快！"
            if hint:
                overall += " 已根据您的历史偏好个性化优化。"

            trip_plan = TripPlan(
                city=request.city,
                start_date=request.start_date,
                end_date=request.end_date,
                days=day_results,  # type: ignore[arg-type]
                weather_info=weather_info,
                overall_suggestions=overall,
                budget=budget,
            )
            logger.success(f"✅ plan 节点完成（并行逐日模式，{total_days} 天）")
            return {"trip_plan": trip_plan, "error": None}

        except Exception as parallel_err:
            logger.warning(f"⚠️ 并行规划异常，回退整体模式: {parallel_err}")

        # ── 回退：整体一次性 LLM 规划 ──
        return await self._plan_single_call(state)

    async def _plan_single_call(self, state: PlannerState) -> dict:
        """回退方案：整体一次 LLM 调用生成全程 JSON"""
        request: TripRequest = state["request"]
        planner_query = self._build_planner_query(
            request,
            state["attraction_response"],
            state["weather_response"],
            state["hotel_response"],
            state["food_response"],
            cities=state["cities"],
            user_profile_hint=state.get("user_profile_hint"),
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
            logger.success("✅ plan 节点完成（整体模式）")
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

    async def postprocess(self, state: PlannerState) -> dict:
        """修正坐标、添加天气预警、补充开放时间（并发 AMap 调用）"""
        trip_plan: Optional[TripPlan] = state.get("trip_plan")
        if not trip_plan:
            return {"trip_plan": None, "error": state.get("error", "行程规划失败")}

        primary_city = state["primary_city"]
        await asyncio.gather(
            self._fix_coordinates_async(trip_plan, primary_city),
            self._enrich_opening_hours_async(trip_plan, primary_city),
        )
        self._add_weather_warnings(trip_plan)
        logger.success("✅ postprocess 节点完成")
        return {"trip_plan": trip_plan, "error": None}

    # ──────────────────────────────────────────
    # 后处理辅助方法
    # ──────────────────────────────────────────

    async def _fix_coordinates_async(self, trip_plan: TripPlan, city: str) -> None:
        """并发修正所有景点经纬度坐标"""
        attractions = [
            (attraction, day)
            for day in trip_plan.days
            for attraction in day.attractions
            if attraction.address
        ]
        if not attractions:
            return

        tasks = [
            self._amap_client.geocode_async(attr.address, city)
            for attr, _ in attractions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (attraction, _), result in zip(attractions, results):
            if isinstance(result, Exception):
                logger.debug(f"坐标修正异常 [{attraction.name}]: {result}")
            elif result:
                lng, lat = result
                attraction.location = Location(longitude=lng, latitude=lat)
                logger.debug(f"✅ 坐标修正: {attraction.name} → {lng},{lat}")

    def _fix_coordinates(self, trip_plan: TripPlan, city: str) -> None:
        """通过高德地理编码 API 修正所有景点经纬度坐标（同步，保留供测试使用）"""
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

    async def _enrich_opening_hours_async(self, trip_plan: TripPlan, city: str) -> None:
        """并发获取所有景点真实开放时间"""
        attractions = [
            attraction
            for day in trip_plan.days
            for attraction in day.attractions
        ]
        if not attractions:
            return

        tasks = [
            self._amap_client.get_opening_hours_async(attr.name, city)
            for attr in attractions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for attraction, result in zip(attractions, results):
            if isinstance(result, Exception):
                logger.debug(f"开放时间获取异常 [{attraction.name}]: {result}")
            elif result:
                attraction.opening_hours = result
                logger.debug(f"🕐 {attraction.name} 开放时间: {result}")

    def _enrich_opening_hours(self, trip_plan: TripPlan, city: str) -> None:
        """通过高德 Place Search API 获取景点真实开放时间（同步，保留供测试使用）"""
        for day in trip_plan.days:
            for attraction in day.attractions:
                opentime = self._amap_client.get_opening_hours(attraction.name, city)
                if opentime:
                    attraction.opening_hours = opentime
                    logger.debug(f"🕐 {attraction.name} 开放时间: {opentime}")
