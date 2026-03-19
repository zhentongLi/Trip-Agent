"""多智能体旅行规划系统 - 基于 LangGraph"""

import asyncio
import json
import re
import random
import requests
from typing import Dict, Any, List, AsyncGenerator, Optional
from loguru import logger

# LangGraph / LangChain
from langgraph.graph import StateGraph, START, END
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import StructuredTool
from typing_extensions import TypedDict

from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings

# ============ Agent 提示词（标准 LangChain 风格，工具由框架自动调用） ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。请使用 search_places 工具搜索指定城市的景点信息。
搜索完成后，以文字形式汇总景点名称、地址、坐标和简要描述，不要遗漏搜索结果中的关键数据。"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。请使用 get_weather 工具查询指定城市的天气预报。
查询完成后，以文字形式汇总每天的天气状况、温度、风向和风力。"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。请使用 search_places 工具搜索指定城市的酒店。
搜索完成后，以文字形式汇总酒店名称、地址、评分和坐标。"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "豆浆油条王（南京路店）", "address": "城市名某某街道1号", "description": "本地特色早点，人均20元", "estimated_cost": 20},
        {"type": "lunch", "name": "陶陶居（正宗粤菜）", "address": "城市名某某路88号", "description": "地道粤式点心，人均80元", "estimated_cost": 80},
        {"type": "dinner", "name": "外婆家（杭帮菜）", "address": "城市名某某广场3楼", "description": "杭帮菜特色，人均100元", "estimated_cost": 100}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐（breakfast/lunch/dinner各一条）
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
8. **餐饮必须包含具体餐厅信息**:
   - name字段写具体餐厅名称（不是"早餐推荐"这样的描述）
   - address字段写具体街道地址
   - description包含食物特色和人均消费描述
9. **只返回JSON，不要有任何其他文字说明**"""

FOOD_AGENT_PROMPT = """你是餐饮推荐专家。请使用 search_places 工具搜索指定城市的餐厅及美食。
搜索完成后，以文字形式汇总餐厅名称、地址、评分和特色菜品信息。"""


# ============ LangGraph 状态定义 ============

class PlannerState(TypedDict):
    """LangGraph 各节点间共享的状态字典"""
    request: TripRequest
    cities: List[str]
    primary_city: str
    attraction_response: str
    weather_response: str
    hotel_response: str
    food_response: str
    trip_plan: Optional[TripPlan]
    error: Optional[str]


# ============ 高德地图工具工厂（替代 MCPTool，直接调用 REST API） ============

def _make_amap_tools(api_key: str) -> tuple:
    """创建高德地图 REST API 工具，无需 MCP 子进程"""

    def _search_places(keywords: str, city: str) -> str:
        """搜索高德地图兴趣点（景点、酒店、餐厅等），按关键词和城市筛选"""
        try:
            resp = requests.get(
                "https://restapi.amap.com/v3/place/text",
                params={"keywords": keywords, "city": city, "output": "json", "key": api_key},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("pois"):
                pois = data["pois"][:10]
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
        except Exception as e:
            return f"查询失败: {e}"

    def _get_weather(city: str) -> str:
        """查询指定城市的未来几天天气预报"""
        try:
            resp = requests.get(
                "https://restapi.amap.com/v3/weather/weatherInfo",
                params={"city": city, "extensions": "all", "output": "json", "key": api_key},
                timeout=10,
            )
            data = resp.json()
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
        except Exception as e:
            return f"天气查询失败: {e}"

    search_places_tool = StructuredTool.from_function(
        func=_search_places,
        name="search_places",
        description="搜索高德地图兴趣点（景点、酒店、餐厅等），按关键词和城市筛选",
    )
    get_weather_tool = StructuredTool.from_function(
        func=_get_weather,
        name="get_weather",
        description="查询指定城市的未来几天天气预报",
    )
    return search_places_tool, get_weather_tool


class MultiAgentTripPlanner:
    """多智能体旅行规划系统（LangGraph 版）"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统（LangGraph）...")

        try:
            settings = get_settings()
            self.llm = get_llm()
            self.amap_api_key = settings.amap_api_key
            # 上游网关偶发 502 时做自动重试；并发收敛可降低瞬时失败概率
            self.max_llm_retries = 3
            self.retry_base_delay = 0.8
            self.llm_call_semaphore = asyncio.Semaphore(2)

            # 创建高德地图 REST API 工具（无需 MCP/uvx 子进程）
            print("  - 创建高德地图 REST API 工具...")
            search_places_tool, get_weather_tool = _make_amap_tools(settings.amap_api_key)

            # 用 create_react_agent 创建四个专项 Agent
            print("  - 创建专项 Agent（LangGraph react agent）...")
            self.attraction_agent = create_agent(
                self.llm,
                tools=[search_places_tool],
                system_prompt=SystemMessage(content=ATTRACTION_AGENT_PROMPT),
            )
            self.weather_agent = create_agent(
                self.llm,
                tools=[get_weather_tool],
                system_prompt=SystemMessage(content=WEATHER_AGENT_PROMPT),
            )
            self.hotel_agent = create_agent(
                self.llm,
                tools=[search_places_tool],
                system_prompt=SystemMessage(content=HOTEL_AGENT_PROMPT),
            )
            self.food_agent = create_agent(
                self.llm,
                tools=[search_places_tool],
                system_prompt=SystemMessage(content=FOOD_AGENT_PROMPT),
            )

            # 构建 LangGraph 主图
            print("  - 构建 LangGraph 状态图（gather → plan → postprocess）...")
            self.graph = self._build_graph()

            print("✅ 多智能体系统初始化成功（LangGraph 版）")
        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    @staticmethod
    def _is_retryable_llm_error(err: Exception) -> bool:
        """判断是否属于可重试的上游临时错误。"""
        msg = str(err).lower()
        retry_tokens = [
            "502", "503", "504",
            "service temporarily unavailable",
            "timeout", "timed out",
            "connection reset",
            "rate limit",
            "too many requests",
        ]
        return any(t in msg for t in retry_tokens)

    async def _invoke_with_retry(self, coro_factory, label: str):
        """包装 LLM 异步调用：限流 + 指数退避 + 抖动重试。"""
        last_err = None
        for attempt in range(1, self.max_llm_retries + 1):
            try:
                async with self.llm_call_semaphore:
                    return await coro_factory()
            except Exception as e:
                last_err = e
                if attempt >= self.max_llm_retries or not self._is_retryable_llm_error(e):
                    raise
                delay = self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                logger.warning(
                    f"{label} 调用失败（第{attempt}/{self.max_llm_retries}次）: {e}，"
                    f"{delay:.2f}s 后重试"
                )
                await asyncio.sleep(delay)
        raise last_err

    # ============ LangGraph 图构建 ============

    def _build_graph(self):
        """构建三节点状态图：gather → plan → postprocess"""
        workflow = StateGraph(PlannerState)
        workflow.add_node("gather", self._gather_node)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("postprocess", self._postprocess_node)
        workflow.add_edge(START, "gather")
        workflow.add_edge("gather", "plan")
        workflow.add_edge("plan", "postprocess")
        workflow.add_edge("postprocess", END)
        return workflow.compile()

    async def _gather_node(self, state: "PlannerState") -> dict:
        """节点1：并行调用四个专项 Agent，收集景点/天气/酒店/餐饮数据"""
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
            attraction_queries.append(f"请搜索{city}的{pref_kw}相关景点，keywords={pref_kw}，city={city}")
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
            *[_invoke(self.attraction_agent, q, f"{cities[i]}景点") for i, q in enumerate(attraction_queries)],
            *[_invoke(self.weather_agent, q, f"{cities[i]}天气") for i, q in enumerate(weather_queries)],
            _invoke(self.hotel_agent, hotel_query, "酒店"),
            _invoke(self.food_agent, food_query, "餐饮"),
        ]
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        n = len(cities[:3])
        attraction_results = all_results[:n]
        weather_results = all_results[n:2 * n]
        hotel_result = all_results[2 * n]
        food_result = all_results[2 * n + 1]

        def _safe(r, label=""):
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

    async def _plan_node(self, state: "PlannerState") -> dict:
        """节点2：调用 planner LLM 整合信息，生成 JSON 行程"""
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
                lambda: self.llm.ainvoke([
                    SystemMessage(content=PLANNER_AGENT_PROMPT),
                    HumanMessage(content=planner_query),
                ]),
                "Planner",
            )
            trip_plan = self._parse_response(response.content, request)
            logger.success("✅ plan 节点完成")
            return {"trip_plan": trip_plan, "error": None}
        except Exception as e:
            if self._is_retryable_llm_error(e):
                logger.warning(f"⚠️ plan 节点失败（上游临时不可用）: {e}")
            else:
                logger.error(f"❌ plan 节点失败: {e}")
            return {"trip_plan": None, "error": str(e)}

    def _postprocess_node(self, state: "PlannerState") -> dict:
        """节点3：坐标修正 + 天气预警 + 开放时间"""
        trip_plan: Optional[TripPlan] = state.get("trip_plan")
        if not trip_plan:
            return {"trip_plan": None, "error": state.get("error", "行程规划失败")}

        primary_city = state["primary_city"]
        self._fix_coordinates(trip_plan, primary_city)
        self._add_weather_warnings(trip_plan)
        self._enrich_opening_hours(trip_plan, primary_city)
        logger.success("✅ postprocess 节点完成")
        return {"trip_plan": trip_plan, "error": None}
    
    def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        同步入口：内部复用 plan_trip_stream 的逻辑（供旧 /plan 路由使用）

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        try:
            logger.info(f"🚀 [同步] 开始规划 {request.city}, {request.travel_days}天")

            async def _collect():
                trip_plan_data = None
                async for event in self.plan_trip_stream(request):
                    if event.get("type") == "done":
                        trip_plan_data = event["data"]
                    elif event.get("type") == "error":
                        raise RuntimeError(event.get("message", "未知错误"))
                return trip_plan_data

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在已有事件循环中使用 run_until_complete 会死锁，改用 asyncio.run_coroutine_threadsafe
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(_collect(), loop)
                    data = future.result(timeout=300)
                else:
                    data = loop.run_until_complete(_collect())
            except RuntimeError:
                data = asyncio.run(_collect())

            if data:
                return TripPlan(**data)
            return self._create_fallback_plan(request)

        except Exception as e:
            logger.error(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)

    async def plan_trip_stream(self, request: TripRequest) -> AsyncGenerator[dict, None]:
        """
        异步流式生成旅行计划（SSE 核心实现 - LangGraph 版）

        通过 graph.astream(stream_mode="updates") 逐节点获取更新，
        将 LangGraph 节点事件转换为前端 SSE 进度事件；
        公共接口与 HelloAgents 版完全一致，路由层零改动。
        """
        from ..services.cache_service import trip_cache, make_trip_cache_key

        # ---------- 缓存检查 ----------
        cache_key = make_trip_cache_key(
            city=request.city,
            cities=request.cities,
            start_date=request.start_date,
            end_date=request.end_date,
            preferences=request.preferences,
            accommodation=request.accommodation,
            transportation=request.transportation,
            budget_limit=request.budget_limit,
        )
        cached_data = trip_cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"⚡ 命中缓存: {cache_key}")
            yield {"type": "progress", "percent": 95, "message": "⚡ 从缓存返回结果，秒级响应..."}
            yield {"type": "done", "data": cached_data}
            return

        # ---------- 初始化 LangGraph 状态 ----------
        cities: List[str] = request.cities if (request.cities and len(request.cities) >= 2) else [request.city]
        primary_city = cities[0]

        initial_state: PlannerState = {
            "request": request,
            "cities": cities,
            "primary_city": primary_city,
            "attraction_response": "",
            "weather_response": "",
            "hotel_response": "",
            "food_response": "",
            "trip_plan": None,
            "error": None,
        }

        yield {"type": "progress", "percent": 5, "message": "🚀 开始规划..."}
        yield {"type": "progress", "percent": 15, "message": f"🔄 并行搜索{'→'.join(cities)} 景点、天气、酒店、餐饮..."}

        try:
            # ---------- LangGraph 图流式执行，逐节点 yield SSE 进度 ----------
            async for chunk in self.graph.astream(initial_state, stream_mode="updates"):
                node_name = next(iter(chunk))
                node_output = chunk[node_name]

                if node_name == "gather":
                    yield {"type": "progress", "percent": 65, "message": "📋 整合信息，生成行程计划..."}

                elif node_name == "plan":
                    if node_output.get("error"):
                        logger.warning(f"plan 节点出错: {node_output['error']}")
                    yield {"type": "progress", "percent": 80, "message": "📍 修正景点坐标 & 天气预警..."}

                elif node_name == "postprocess":
                    trip_plan: Optional[TripPlan] = node_output.get("trip_plan")
                    if trip_plan and not node_output.get("error"):
                        trip_cache.set(cache_key, trip_plan.model_dump())
                        logger.success(f"💾 已写入缓存: {cache_key}")
                        yield {"type": "progress", "percent": 100, "message": "✅ 完成！"}
                        yield {"type": "done", "data": trip_plan.model_dump()}
                    else:
                        fallback = self._create_fallback_plan(request)
                        err_msg = node_output.get("error", "行程规划失败")
                        if self._is_retryable_llm_error(RuntimeError(err_msg)):
                            # 上游临时故障时优雅降级，避免前端被 error 事件打断。
                            logger.warning(f"⚠️ 上游模型临时不可用，返回备用行程: {err_msg}")
                            yield {
                                "type": "progress",
                                "percent": 100,
                                "message": "⚠️ 模型服务暂时拥堵，已返回备用行程",
                            }
                        else:
                            yield {"type": "error", "message": err_msg}
                        yield {"type": "done", "data": fallback.model_dump()}

        except Exception as e:
            logger.error(f"❌ 流式规划失败: {e}")
            import traceback
            traceback.print_exc()
            fallback = self._create_fallback_plan(request)
            yield {"type": "error", "message": str(e)}
            yield {"type": "done", "data": fallback.model_dump()}

    
    def _fix_coordinates(self, trip_plan: TripPlan, city: str) -> None:
        """使用高德 REST 地理编码 API 修正所有景点的经纬度坐标"""
        for day in trip_plan.days:
            for attraction in day.attractions:
                if not attraction.address:
                    continue
                try:
                    resp = requests.get(
                        "https://restapi.amap.com/v3/geocode/geo",
                        params={"address": attraction.address, "city": city, "key": self.amap_api_key},
                        timeout=5
                    )
                    data = resp.json()
                    if data.get("status") == "1" and data.get("geocodes"):
                        lng, lat = data["geocodes"][0]["location"].split(",")
                        attraction.location = Location(longitude=float(lng), latitude=float(lat))
                        logger.debug(f"✅ 坐标修正: {attraction.name} → {lng},{lat}")
                except Exception as e:
                    logger.warning(f"⚠️ 坐标修正失败 [{attraction.name}]: {e}")

    def _add_weather_warnings(self, trip_plan: TripPlan) -> None:
        """#13 天气预警：检测极端天气并为每日天气信息添加预警标签"""
        extreme_keywords = ["暴雨", "大暴雨", "特大暴雨", "台风", "暴雪", "大雪", "冰雪", "沙尘暴", "冰暴", "龙卷风"]
        HIGH_TEMP = 35   # °C
        LOW_TEMP = -10   # °C

        for weather in trip_plan.weather_info:
            warnings: List[str] = []

            # 检查天气文字
            combined_weather = (weather.day_weather or "") + " " + (weather.night_weather or "")
            for kw in extreme_keywords:
                if kw in combined_weather:
                    warnings.append(f"⚠️ {kw}预警")
                    break  # 只取第一个匹配的极端天气

            # 高温 / 严寒
            try:
                temp = int(weather.day_temp) if isinstance(weather.day_temp, str) else weather.day_temp
                if temp > HIGH_TEMP:
                    warnings.append(f"🌡️ 高温预警（{temp}°C）")
                elif temp < LOW_TEMP:
                    warnings.append(f"❄️ 严寒预警（{temp}°C）")
            except (ValueError, TypeError):
                pass

            # 大风（≥7级）
            m = re.search(r"(\d+)", str(weather.wind_power or ""))
            if m and int(m.group(1)) >= 7:
                warnings.append(f"💨 大风预警（{weather.wind_power}）")

            if warnings:
                weather.weather_warning = "；".join(warnings)
                logger.warning(f"🚨 {weather.date} 天气预警: {weather.weather_warning}")

    def _enrich_opening_hours(self, trip_plan: TripPlan, city: str) -> None:
        """#12 实时价格接入：通过高德 Place Search API 获取景点真实开放时间"""
        for day in trip_plan.days:
            for attraction in day.attractions:
                try:
                    resp = requests.get(
                        "https://restapi.amap.com/v3/place/text",
                        params={
                            "keywords": attraction.name,
                            "city": city,
                            "output": "json",
                            "key": self.amap_api_key,
                        },
                        timeout=5,
                    )
                    data = resp.json()
                    if data.get("status") == "1" and data.get("pois"):
                        poi = data["pois"][0]
                        biz = poi.get("biz_ext") or {}
                        opentime = (
                            biz.get("opentime")
                            or poi.get("business_area")
                            or ""
                        )
                        if opentime:
                            attraction.opening_hours = opentime
                            logger.debug(f"🕐 {attraction.name} 开放时间: {opentime}")
                except Exception as e:
                    logger.debug(f"获取开放时间失败 [{attraction.name}]: {e}")


    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询"""
        if request.preferences:
            keywords = request.preferences[0]
        else:
            keywords = "景点"

        # 只传自然语言问题，让Agent根据system_prompt自行输出[TOOL_CALL:]格式
        query = f"请搜索{request.city}的{keywords}相关景点，使用amap_maps_text_search工具，city={request.city}，keywords={keywords}"
        return query

    def _build_planner_query(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str = "",
        foods: str = "",
        cities: Optional[List[str]] = None,
    ) -> str:
        """构建行程规划查询（支持多城市、预算约束）"""
        from datetime import datetime, timedelta

        city_list = cities if cities and len(cities) >= 2 else [request.city]
        city_display = " → ".join(city_list) if len(city_list) > 1 else request.city
        is_multi_city = len(city_list) > 1
        total_days = request.travel_days

        query = f"""请根据以下信息生成{city_display}的{total_days}天旅行计划:

**基本信息:**
- 目的地: {city_display}{'（多城市联游）' if is_multi_city else ''}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {total_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}"""

        if request.budget_limit:
            query += f"\n- **预算上限: {request.budget_limit}元**（优先安排免票/低价景点，住宿选经济型）"

        if is_multi_city:
            # 计算每个城市分配的天数
            days_per_city = max(1, total_days // len(city_list))
            remainder = total_days - days_per_city * len(city_list)
            city_day_ranges = []
            start = datetime.strptime(request.start_date, "%Y-%m-%d")
            current = start
            for idx, city in enumerate(city_list):
                days = days_per_city + (1 if idx < remainder else 0)
                end = current + timedelta(days=days - 1)
                city_day_ranges.append(
                    f"- **{city}**：第{(current - start).days + 1}天 ～ 第{(end - start).days + 1}天"
                    f"（{current.strftime('%m/%d')} ~ {end.strftime('%m/%d')}，共{days}天）"
                )
                current = end + timedelta(days=1)
            query += f"""

**多城市路线安排（必须严格按以下分配）:**
{chr(10).join(city_day_ranges)}
- 每个城市使用该城市自己的景点信息，不要跨城混排
- 城市切换当天请在 description 中写明跨城交通方式（如：08:00 乘高铁从XX出发，约X小时到达XX）"""

        query += f"""

**景点信息（按城市分组）:**
{attractions}

**天气信息（按城市分组）:**
{weather}

**酒店信息:**
{hotels}

**餐饮信息（以下是真实搜索到的餐厅，请从中选择具体餐厅名称）:**
{foods}

**严格要求（必须全部满足）:**
1. 每天安排2-3个具体景点（名称、地址、坐标、描述、门票价格）
2. 每天必须包含3条 meals：type分别为 breakfast / lunch / dinner，缺一不可
3. meals 中 name 字段必须是具体餐厅名称（如"外婆家·滨江店"），不能写"早餐推荐"这类描述
4. meals 中 description 字段说明特色菜品和人均消费，estimated_cost 填数字
5. 每天推荐一个具体酒店（从酒店信息中选）
6. **只返回纯 JSON，不要有任何说明文字、Markdown 标题或代码块之外的内容**"""

        if request.budget_limit:
            query += f"\n7. 所有花费合计必须控制在 {request.budget_limit} 元以内"

        if is_multi_city:
            query += f"\n8. 多城市行程：city 字段填写主城市（{city_list[0]}），每天的 description 标注当前城市"

        if request.free_text_input:
            query += f"\n\n**额外要求:** {request.free_text_input}"

        return query

    
    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应为 TripPlan 对象。
        尝试多种 JSON 提取策略，并在失败时详细记录错误。
        """
        raw_preview = response[:300].replace("\n", "\\n") if response else "(empty)"
        logger.debug(f"📄 planner_response 前300字符: {raw_preview}")

        def _extract_json_str(text: str) -> str:
            """从文本中尽力提取 JSON 字符串"""
            # 优先找 ```json ... ``` 块
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
            # 找普通 ``` ... ``` 块
            if "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                if end > start:
                    candidate = text[start:end].strip()
                    if candidate.startswith("{"):
                        return candidate
            # 直接找最外层 { ... }
            if "{" in text:
                brace_count = 0
                start_idx = text.find("{")
                for i, ch in enumerate(text[start_idx:], start_idx):
                    if ch == "{":
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            return text[start_idx: i + 1]
            raise ValueError("响应中未找到 JSON 数据")

        try:
            json_str = _extract_json_str(response)
            data = json.loads(json_str)
            # 用 model_validate 代替 **data，支持 extra fields & 宽松模式
            trip_plan = TripPlan.model_validate(data)
            logger.success("✅ planner 响应 JSON 解析成功")
            return trip_plan
        except Exception as e:
            logger.warning(f"⚠️  解析响应失败 ({type(e).__name__}: {e})，将使用备用方案")
            logger.debug(f"📄 完整 planner_response:\n{response[:2000]}")
            return self._create_fallback_plan(request)
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)，支持多城市"""
        from datetime import datetime, timedelta

        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        # 确定城市列表（多城市模式）
        city_list = (request.cities or []) if (request.cities and len(request.cities) >= 2) else [request.city]
        total_days = request.travel_days

        # 各城市分配天数
        days_per_city = max(1, total_days // len(city_list))
        remainder = total_days - days_per_city * len(city_list)
        city_schedule: List[str] = []
        for idx, city in enumerate(city_list):
            days = days_per_city + (1 if idx < remainder else 0)
            city_schedule.extend([city] * days)

        # 各城市中心坐标（用于fallback时生成合理坐标）
        city_centers: Dict[str, tuple] = {
            "北京": (116.397, 39.916), "上海": (121.473, 31.230),
            "广州": (113.264, 23.129), "深圳": (114.058, 22.543),
            "杭州": (120.153, 30.287), "成都": (104.065, 30.659),
            "西安": (108.940, 34.341), "武汉": (114.298, 30.584),
            "南京": (118.796, 32.059), "重庆": (106.551, 29.563),
        }

        # 餐厅名称模板（按城市特色）
        meal_templates: Dict[str, Dict[str, str]] = {
            "北京": {"breakfast": "老北京豆汁店", "lunch": "全聚德烤鸭（前门店）", "dinner": "簋街海鲜小龙虾"},
            "上海": {"breakfast": "沈大成点心店", "lunch": "南翔馒头店", "dinner": "外婆家（新天地店）"},
            "广州": {"breakfast": "泮溪酒家早茶", "lunch": "陶陶居（正宗粤菜）", "dinner": "荔湾艇仔粥"},
            "深圳": {"breakfast": "喜茶·海岸城店", "lunch": "大家乐茶餐厅", "dinner": "海上世界夜市"},
            "杭州": {"breakfast": "知味观小笼包店", "lunch": "外婆家·西湖店", "dinner": "河坊街特色小吃"},
            "成都": {"breakfast": "谭豆花（成都特色早餐）", "lunch": "陈麻婆豆腐总店", "dinner": "宽窄巷子火锅"},
            "西安": {"breakfast": "贾三灌汤包子馆", "lunch": "同盛祥泡馍馆", "dinner": "回民街羊肉烤串"},
        }

        days = []
        for i in range(total_days):
            current_date = start_date + timedelta(days=i)
            current_city = city_schedule[i] if i < len(city_schedule) else request.city
            lng_base, lat_base = city_centers.get(current_city, (116.4, 39.9))

            tmpl = meal_templates.get(current_city, {
                "breakfast": f"{current_city}特色早餐馆",
                "lunch": f"{current_city}风味午餐厅",
                "dinner": f"{current_city}特色晚餐馆",
            })

            day_desc = f"第{i+1}天 · {current_city}行程"
            if len(city_list) > 1 and i > 0 and city_schedule[i] != city_schedule[i - 1]:
                prev_city = city_schedule[i - 1]
                day_desc = f"第{i+1}天 · 从{prev_city}前往{current_city}（建议乘高铁/飞机）"

            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=day_desc,
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{current_city}著名景点{j+1}（待规划）",
                        address=f"{current_city}市区",
                        location=Location(
                            longitude=round(lng_base + i * 0.01 + j * 0.005, 6),
                            latitude=round(lat_base + i * 0.01 + j * 0.005, 6),
                        ),
                        visit_duration=120,
                        description=f"这是{current_city}的著名景点，具体信息请联网重新规划",
                        category="景点",
                        ticket_price=0,
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(
                        type="breakfast",
                        name=tmpl["breakfast"],
                        address=f"{current_city}市区",
                        description=f"{current_city}特色早餐，人均约25元",
                        estimated_cost=25,
                    ),
                    Meal(
                        type="lunch",
                        name=tmpl["lunch"],
                        address=f"{current_city}市区",
                        description=f"{current_city}特色午餐，人均约80元",
                        estimated_cost=80,
                    ),
                    Meal(
                        type="dinner",
                        name=tmpl["dinner"],
                        address=f"{current_city}市区夜市",
                        description=f"{current_city}特色晚餐，人均约100元",
                        estimated_cost=100,
                    ),
                ],
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=(
                f"这是为您规划的{'→'.join(city_list)}{total_days}日游行程（备用方案），"
                f"建议重新提交以获取完整的AI规划。"
            ),
        )


    async def adjust_trip(self, trip_plan: "TripPlan", user_message: str, city: str = "") -> "TripPlan":
        """
        功能20：AI 行程调整对话
        接收当前行程 + 用户自然语言要求，返回修改后的行程。

        Args:
            trip_plan: 当前 TripPlan 对象
            user_message: 用户的调整要求（自然语言）
            city: 主要城市（用于坐标修正，可选）

        Returns:
            修改后的 TripPlan
        """
        logger.info(f"🔧 AI 行程调整: [{user_message[:60]}]")

        current_plan_json = trip_plan.model_dump_json(indent=2)

        adjust_prompt = f"""你是行程修改专家。以下是用户当前的旅行行程（JSON 格式），请根据用户要求进行修改。

**当前行程：**
```json
{current_plan_json}
```

**用户要求：**
{user_message}

**修改规则：**
1. 只修改用户明确要求的部分，其他内容保持不变
2. 保持 JSON 结构完整，所有必填字段不能缺失
3. 修改景点时，保持 location 坐标合理（可使用原坐标附近的值）
4. 每天必须保持 breakfast / lunch / dinner 三条 meals
5. **只返回修改后的完整 JSON，不要有任何说明文字**

请直接返回修改后的完整行程 JSON："""

        try:
            response = await self._invoke_with_retry(
                lambda: self.llm.ainvoke([
                    SystemMessage(content="你是专业的旅行行程修改专家，严格按照用户要求修改 JSON 格式行程。"),
                    HumanMessage(content=adjust_prompt),
                ]),
                "AdjustTrip",
            )
            adjusted_plan = self._parse_adjust_response(response.content, trip_plan)
            if city:
                self._fix_coordinates(adjusted_plan, city)
            logger.success("✅ AI 行程调整完成")
            return adjusted_plan
        except Exception as e:
            logger.error(f"❌ AI 行程调整失败: {e}")
            raise

    def _parse_adjust_response(self, response: str, original_plan: "TripPlan") -> "TripPlan":
        """解析行程调整响应，失败时返回原始行程"""
        try:
            # 复用已有的 JSON 提取逻辑
            def _extract_json_str(text: str) -> str:
                if "```json" in text:
                    start = text.find("```json") + 7
                    end = text.find("```", start)
                    if end > start:
                        return text[start:end].strip()
                if "```" in text:
                    start = text.find("```") + 3
                    end = text.find("```", start)
                    if end > start:
                        candidate = text[start:end].strip()
                        if candidate.startswith("{"):
                            return candidate
                if "{" in text:
                    brace_count = 0
                    start_idx = text.find("{")
                    for i, ch in enumerate(text[start_idx:], start_idx):
                        if ch == "{":
                            brace_count += 1
                        elif ch == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                return text[start_idx:i + 1]
                raise ValueError("未找到 JSON 数据")

            json_str = _extract_json_str(response)
            data = json.loads(json_str)
            from ..models.schemas import TripPlan
            return TripPlan.model_validate(data)
        except Exception as e:
            logger.warning(f"⚠️ 调整响应解析失败（{e}），返回原始行程")
            return original_plan


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner

