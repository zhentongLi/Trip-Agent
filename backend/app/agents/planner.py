"""多智能体旅行规划系统 - 精简编排器（LangGraph 版）

职责：
  - 构建 AmapRestClient、NodeFactory、各 Agent、LangGraph 图
  - 提供 plan_trip_stream / plan_trip / adjust_trip 三个公共接口
  - LLM 调用限流 + 重试（_invoke_with_retry）
  - Fallback 行程生成（_create_fallback_plan）
  - 多城市行程 Query 构建（_build_planner_query）

依赖模块：
  agents/nodes.py     - NodeFactory（gather / plan / postprocess 节点）
  agents/parsers.py   - parse_adjust_response
  agents/prompts.py   - 提示词常量
  agents/tools.py     - make_amap_tools
  services/amap_rest_client.py - AmapRestClient（含熔断器）
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from loguru import logger

from ..models.schemas import (
    Attraction,
    DayPlan,
    Hotel,
    Location,
    Meal,
    TripPlan,
    TripRequest,
    WeatherInfo,
)
from ..services.amap_rest_client import AmapRestClient
from .nodes import NodeFactory
from .parsers import parse_adjust_response
from .prompts import (
    ATTRACTION_AGENT_PROMPT,
    FOOD_AGENT_PROMPT,
    HOTEL_AGENT_PROMPT,
    WEATHER_AGENT_PROMPT,
)
from .state import PlannerState
from .tools import make_amap_tools

# LLM 重试配置
_MAX_LLM_RETRIES = 3
_RETRY_BASE_DELAY = 0.8

# 可重试的上游错误关键词
_RETRYABLE_TOKENS = [
    "502", "503", "504",
    "service temporarily unavailable",
    "timeout", "timed out",
    "connection reset",
    "rate limit",
    "too many requests",
]

# 常见城市备用坐标（fallback 行程使用）
_CITY_CENTERS: Dict[str, tuple[float, float]] = {
    "北京": (116.397, 39.916), "上海": (121.473, 31.230),
    "广州": (113.264, 23.129), "深圳": (114.058, 22.543),
    "杭州": (120.153, 30.287), "成都": (104.065, 30.659),
    "西安": (108.940, 34.341), "武汉": (114.298, 30.584),
    "南京": (118.796, 32.059), "重庆": (106.551, 29.563),
}

_MEAL_TEMPLATES: Dict[str, Dict[str, str]] = {
    "北京": {"breakfast": "老北京豆汁店", "lunch": "全聚德烤鸭（前门店）", "dinner": "簋街海鲜小龙虾"},
    "上海": {"breakfast": "沈大成点心店", "lunch": "南翔馒头店", "dinner": "外婆家（新天地店）"},
    "广州": {"breakfast": "泮溪酒家早茶", "lunch": "陶陶居（正宗粤菜）", "dinner": "荔湾艇仔粥"},
    "深圳": {"breakfast": "喜茶·海岸城店", "lunch": "大家乐茶餐厅", "dinner": "海上世界夜市"},
    "杭州": {"breakfast": "知味观小笼包店", "lunch": "外婆家·西湖店", "dinner": "河坊街特色小吃"},
    "成都": {"breakfast": "谭豆花（成都特色早餐）", "lunch": "陈麻婆豆腐总店", "dinner": "宽窄巷子火锅"},
    "西安": {"breakfast": "贾三灌汤包子馆", "lunch": "同盛祥泡馍馆", "dinner": "回民街羊肉烤串"},
}


def _is_retryable_llm_error(err: Exception) -> bool:
    """判断是否属于可重试的上游临时错误"""
    msg = str(err).lower()
    return any(t in msg for t in _RETRYABLE_TOKENS)


class MultiAgentTripPlanner:
    """多智能体旅行规划编排器（LangGraph 版）"""

    def __init__(self, llm: ChatOpenAI, amap_client: AmapRestClient) -> None:
        logger.info("🔄 初始化多智能体旅行规划系统（LangGraph）...")

        self._llm = llm
        self._amap_client = amap_client
        self._llm_call_semaphore = asyncio.Semaphore(2)

        # 创建 LangChain 工具
        search_tool, weather_tool = make_amap_tools(amap_client)

        # 创建四个专项 Agent
        self._attraction_agent = create_agent(
            llm, tools=[search_tool],
            system_prompt=SystemMessage(content=ATTRACTION_AGENT_PROMPT),
        )
        self._weather_agent = create_agent(
            llm, tools=[weather_tool],
            system_prompt=SystemMessage(content=WEATHER_AGENT_PROMPT),
        )
        self._hotel_agent = create_agent(
            llm, tools=[search_tool],
            system_prompt=SystemMessage(content=HOTEL_AGENT_PROMPT),
        )
        self._food_agent = create_agent(
            llm, tools=[search_tool],
            system_prompt=SystemMessage(content=FOOD_AGENT_PROMPT),
        )

        # 构建节点工厂
        self._node_factory = NodeFactory(
            attraction_agent=self._attraction_agent,
            weather_agent=self._weather_agent,
            hotel_agent=self._hotel_agent,
            food_agent=self._food_agent,
            llm=llm,
            amap_client=amap_client,
            invoke_with_retry=self._invoke_with_retry,
            is_retryable_llm_error=_is_retryable_llm_error,
            build_planner_query=self._build_planner_query,
            create_fallback_plan=self._create_fallback_plan,
        )

        # 构建 LangGraph 状态图
        self._graph = self._build_graph()
        logger.success("✅ 多智能体系统初始化成功（LangGraph 版）")

    # ──────────────────────────────────────────
    # LLM 调用：限流 + 指数退避重试
    # ──────────────────────────────────────────

    async def _invoke_with_retry(self, coro_factory, label: str):
        """限流 + 指数退避 + 抖动重试"""
        last_err: Exception | None = None
        for attempt in range(1, _MAX_LLM_RETRIES + 1):
            try:
                async with self._llm_call_semaphore:
                    return await coro_factory()
            except Exception as e:
                last_err = e
                if attempt >= _MAX_LLM_RETRIES or not _is_retryable_llm_error(e):
                    raise
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                logger.warning(
                    f"{label} 调用失败（第{attempt}/{_MAX_LLM_RETRIES}次）: {e}，"
                    f"{delay:.2f}s 后重试"
                )
                await asyncio.sleep(delay)
        raise last_err  # type: ignore[misc]

    # ──────────────────────────────────────────
    # LangGraph 图构建
    # ──────────────────────────────────────────

    def _build_graph(self):
        workflow = StateGraph(PlannerState)
        workflow.add_node("gather",      self._node_factory.gather)
        workflow.add_node("plan",        self._node_factory.plan)
        workflow.add_node("postprocess", self._node_factory.postprocess)
        workflow.add_edge(START, "gather")
        workflow.add_edge("gather", "plan")
        workflow.add_edge("plan", "postprocess")
        workflow.add_edge("postprocess", END)
        return workflow.compile()

    # ──────────────────────────────────────────
    # 公开接口：流式规划
    # ──────────────────────────────────────────

    async def plan_trip_stream(
        self, request: TripRequest, cache=None
    ) -> AsyncGenerator[dict, None]:
        """异步流式生成旅行计划（SSE 核心）

        Args:
            request: 旅行请求
            cache:   可选 TTLCache 实例；传入时启用缓存读写
        """
        # 缓存检查
        cache_key: Optional[str] = None
        if cache is not None:
            from ..services.cache_service import make_trip_cache_key
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
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info(f"⚡ 命中缓存: {cache_key}")
                yield {"type": "progress", "percent": 95, "message": "⚡ 从缓存返回结果，秒级响应..."}
                yield {"type": "done", "data": cached}
                return

        cities: List[str] = (
            request.cities if (request.cities and len(request.cities) >= 2)
            else [request.city]
        )
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

        yield {"type": "progress", "percent": 5,  "message": "🚀 开始规划..."}
        yield {"type": "progress", "percent": 15, "message": f"🔄 并行搜索{'→'.join(cities)} 景点、天气、酒店、餐饮..."}

        try:
            async for chunk in self._graph.astream(initial_state, stream_mode="updates"):
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
                        if cache is not None and cache_key:
                            cache.set(cache_key, trip_plan.model_dump())
                            logger.success(f"💾 已写入缓存: {cache_key}")
                        yield {"type": "progress", "percent": 100, "message": "✅ 完成！"}
                        yield {"type": "done", "data": trip_plan.model_dump()}
                    else:
                        fallback = self._create_fallback_plan(request)
                        err_msg = node_output.get("error", "行程规划失败")
                        if _is_retryable_llm_error(RuntimeError(err_msg)):
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

    # ──────────────────────────────────────────
    # 公开接口：同步规划（供旧 /plan 路由）
    # ──────────────────────────────────────────

    def plan_trip(self, request: TripRequest, cache=None) -> TripPlan:
        """同步入口，复用 plan_trip_stream 逻辑"""
        try:
            async def _collect():
                async for event in self.plan_trip_stream(request, cache=cache):
                    if event.get("type") == "done":
                        return event["data"]
                    if event.get("type") == "error":
                        raise RuntimeError(event.get("message", "未知错误"))
                return None

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
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
            logger.error(f"❌ 生成旅行计划失败: {e}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)

    # ──────────────────────────────────────────
    # 公开接口：AI 行程调整
    # ──────────────────────────────────────────

    async def adjust_trip(
        self, trip_plan: TripPlan, user_message: str, city: str = ""
    ) -> TripPlan:
        """接收当前行程 + 用户自然语言要求，返回修改后的行程"""
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

        response = await self._invoke_with_retry(
            lambda: self._llm.ainvoke([
                SystemMessage(content="你是专业的旅行行程修改专家，严格按照用户要求修改 JSON 格式行程。"),
                HumanMessage(content=adjust_prompt),
            ]),
            "AdjustTrip",
        )
        adjusted = parse_adjust_response(response.content, trip_plan)
        if city:
            self._node_factory._fix_coordinates(adjusted, city)
        logger.success("✅ AI 行程调整完成")
        return adjusted

    # ──────────────────────────────────────────
    # 内部：多城市 Planner Query 构建
    # ──────────────────────────────────────────

    def _build_planner_query(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str = "",
        foods: str = "",
        cities: Optional[List[str]] = None,
    ) -> str:
        city_list = cities if cities and len(cities) >= 2 else [request.city]
        city_display = " → ".join(city_list) if len(city_list) > 1 else request.city
        is_multi_city = len(city_list) > 1
        total_days = request.travel_days

        query = (
            f"请根据以下信息生成{city_display}的{total_days}天旅行计划:\n\n"
            f"**基本信息:**\n"
            f"- 目的地: {city_display}{'（多城市联游）' if is_multi_city else ''}\n"
            f"- 日期: {request.start_date} 至 {request.end_date}\n"
            f"- 天数: {total_days}天\n"
            f"- 交通方式: {request.transportation}\n"
            f"- 住宿: {request.accommodation}\n"
            f"- 偏好: {', '.join(request.preferences) if request.preferences else '无'}"
        )

        if request.budget_limit:
            query += f"\n- **预算上限: {request.budget_limit}元**（优先安排免票/低价景点，住宿选经济型）"

        if is_multi_city:
            days_per_city = max(1, total_days // len(city_list))
            remainder = total_days - days_per_city * len(city_list)
            ranges: List[str] = []
            start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
            current = start_dt
            for idx, city in enumerate(city_list):
                days = days_per_city + (1 if idx < remainder else 0)
                end_dt = current + timedelta(days=days - 1)
                ranges.append(
                    f"- **{city}**：第{(current - start_dt).days + 1}天 ～ 第{(end_dt - start_dt).days + 1}天"
                    f"（{current.strftime('%m/%d')} ~ {end_dt.strftime('%m/%d')}，共{days}天）"
                )
                current = end_dt + timedelta(days=1)
            query += (
                f"\n\n**多城市路线安排（必须严格按以下分配）:**\n"
                + "\n".join(ranges)
                + "\n- 每个城市使用该城市自己的景点信息，不要跨城混排"
                + "\n- 城市切换当天请在 description 中写明跨城交通方式"
            )

        query += (
            f"\n\n**景点信息（按城市分组）:**\n{attractions}"
            f"\n\n**天气信息（按城市分组）:**\n{weather}"
            f"\n\n**酒店信息:**\n{hotels}"
            f"\n\n**餐饮信息（以下是真实搜索到的餐厅，请从中选择具体餐厅名称）:**\n{foods}"
            f"\n\n**严格要求（必须全部满足）:**\n"
            "1. 每天安排2-3个具体景点（名称、地址、坐标、描述、门票价格）\n"
            "2. 每天必须包含3条 meals：type分别为 breakfast / lunch / dinner，缺一不可\n"
            "3. meals 中 name 字段必须是具体餐厅名称，不能写描述\n"
            "4. meals 中 description 字段说明特色菜品和人均消费，estimated_cost 填数字\n"
            "5. 每天推荐一个具体酒店\n"
            "6. **只返回纯 JSON，不要有任何说明文字、Markdown 标题或代码块之外的内容**"
        )

        if request.budget_limit:
            query += f"\n7. 所有花费合计必须控制在 {request.budget_limit} 元以内"

        if is_multi_city:
            query += f"\n8. 多城市行程：city 字段填写主城市（{city_list[0]}），每天的 description 标注当前城市"

        if request.free_text_input:
            query += f"\n\n**额外要求:** {request.free_text_input}"

        return query

    # ──────────────────────────────────────────
    # 内部：Fallback 行程生成
    # ──────────────────────────────────────────

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """当 Agent 失败时生成备用行程，支持多城市"""
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        city_list = (
            request.cities if (request.cities and len(request.cities) >= 2)
            else [request.city]
        )
        total_days = request.travel_days

        days_per_city = max(1, total_days // len(city_list))
        remainder = total_days - days_per_city * len(city_list)
        city_schedule: List[str] = []
        for idx, city in enumerate(city_list):
            days = days_per_city + (1 if idx < remainder else 0)
            city_schedule.extend([city] * days)

        city_centers: Dict[str, tuple[float, float]] = dict(_CITY_CENTERS)

        days: List[DayPlan] = []
        for i in range(total_days):
            current_date = start_date + timedelta(days=i)
            current_city = city_schedule[i] if i < len(city_schedule) else request.city
            if current_city not in city_centers:
                coords = self._node_factory._geocode_city_center(current_city)
                city_centers[current_city] = coords
            lng_base, lat_base = city_centers[current_city]

            tmpl = _MEAL_TEMPLATES.get(current_city, {
                "breakfast": f"{current_city}特色早餐馆",
                "lunch": f"{current_city}风味午餐厅",
                "dinner": f"{current_city}特色晚餐馆",
            })

            day_desc = f"第{i+1}天 · {current_city}行程"
            if len(city_list) > 1 and i > 0 and city_schedule[i] != city_schedule[i - 1]:
                prev_city = city_schedule[i - 1]
                day_desc = f"第{i+1}天 · 从{prev_city}前往{current_city}（建议乘高铁/飞机）"

            days.append(DayPlan(
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
                    Meal(type="breakfast", name=tmpl["breakfast"],
                         address=f"{current_city}市区",
                         description=f"{current_city}特色早餐，人均约25元", estimated_cost=25),
                    Meal(type="lunch", name=tmpl["lunch"],
                         address=f"{current_city}市区",
                         description=f"{current_city}特色午餐，人均约80元", estimated_cost=80),
                    Meal(type="dinner", name=tmpl["dinner"],
                         address=f"{current_city}市区夜市",
                         description=f"{current_city}特色晚餐，人均约100元", estimated_cost=100),
                ],
            ))

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
