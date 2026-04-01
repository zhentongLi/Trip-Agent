# Agent 数据传递流程指南

## 一、核心概览

本项目采用 **LangGraph 三节点工作流**（gather → plan → postprocess）实现多 Agent 协作。各 Agent 通过共享状态字典 **PlannerState** 传递数据，确保信息流在各阶段无缝衔接。

### 数据流核心机制
- **共享状态对象**：PlannerState（TypedDict），承载所有中间数据
- **三个阶段**：
  1. **gather** — 并发调用四个专项 Agent，收集景点/天气/酒店/餐饮数据
  2. **plan** — Planner LLM 汇总信息，生成 JSON 行程
  3. **postprocess** — 坐标修正、天气预警、开放时间增强
- **输出**：plan_trip_stream 通过 SSE 流式输出进度，最终缓存结果

---

## 二、数据流 ASCII 图

```
┌─────────────────────────────────────────────────────────────┐
│                       输入：TripRequest                       │
│          (城市、日期、预算、偏好、住宿、交通等)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
       ┌─────────────────────────────────────┐
       │      初始化 PlannerState             │
       │  - request, cities, primary_city    │
       │  - attraction/weather/hotel/food_   │
       │    response (空)                    │
       │  - trip_plan, error (空)            │
       └────────────────┬────────────────────┘
                        │
                        ▼
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃    gather 节点（并发调用四路）   ┃
    ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
    ┃ ┌─────────────────────────────┐ ┃
    ┃ │ attraction_agent            │ ┃
    ┃ │ + search_places tool        │ ┃  ──► attraction_response
    ┃ └─────────────────────────────┘ ┃
    ┃ ┌─────────────────────────────┐ ┃
    ┃ │ weather_agent               │ ┃
    ┃ │ + get_weather tool          │ ┃  ──► weather_response
    ┃ └─────────────────────────────┘ ┃
    ┃ ┌─────────────────────────────┐ ┃
    ┃ │ hotel_agent                 │ ┃
    ┃ │ + search_places tool        │ ┃  ──► hotel_response
    ┃ └─────────────────────────────┘ ┃
    ┃ ┌─────────────────────────────┐ ┃
    ┃ │ food_agent                  │ ┃
    ┃ │ + search_places tool        │ ┃  ──► food_response
    ┃ └─────────────────────────────┘ ┃
    ┃                                  ┃
    ┃ 并发机制：asyncio.gather(...,    ┃
    ┃           return_exceptions=True) ┃
    ┃ 容错降级：异常 ──► "暂无XXX数据" ┃
    ┗━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━┛
                   │
                   ▼ (PlannerState 填充四个 response 字段)
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃     plan 节点（Planner LLM）     ┃
    ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
    ┃ 输入：                            ┃
    ┃  - attraction_response            ┃
    ┃  - weather_response               ┃
    ┃  - hotel_response                 ┃
    ┃  - food_response                  ┃
    ┃                                   ┃
    ┃ 处理：                            ┃
    ┃  1. 构建 planner_query             ┃
    ┃  2. 调用 Planner LLM              ┃
    ┃  3. 多策略 JSON 提取              ┃
    ┃  4. TripPlan 验证与解析            ┃
    ┃                                   ┃
    ┃ 输出：                            ┃
    ┃  - trip_plan 或 error             ┃
    ┃  (Pydantic 字段校验)              ┃
    ┗━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━┛
                   │
                   ▼ (PlannerState.trip_plan 赋值)
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃  postprocess 节点（后处理增强）   ┃
    ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
    ┃ 输入：trip_plan (from plan node)  ┃
    ┃                                   ┃
    ┃ 三大处理步骤：                    ┃
    ┃  1. _fix_coordinates()            ┃
    ┃     ├─ 遍历 attractions           ┃
    ┃     └─ 调用高德地理编码 API 修正坐标
    ┃                                   ┃
    ┃  2. _add_weather_warnings()       ┃
    ┃     ├─ 检测极端天气关键词         ┃
    ┃     ├─ 高温/严寒预警              ┃
    ┃     └─ 大风预警（≥7级）           ┃
    ┃                                   ┃
    ┃  3. _enrich_opening_hours()       ┃
    ┃     └─ 调用高德 Place Search API  ┃
    ┃        获取实时开放时间            ┃
    ┃                                   ┃
    ┃ 输出：增强后的 TripPlan           ┃
    ┗━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━┛
                   │
                   ▼
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃  plan_trip_stream (SSE + 缓存)   ┃
    ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
    ┃ 逐步 yield 进度事件：              ┃
    ┃  - progress (5%):  "🚀 开始规划"  ┃
    ┃  - progress (15%): "🔄 搜索信息" ┃
    ┃  - progress (65%): "📋 整合信息" ┃
    ┃  - progress (80%): "📍 修正坐标" ┃
    ┃  - progress (100%): "✅ 完成"     ┃
    ┃  - done: {data: TripPlan}         ┃
    ┃                                   ┃
    ┃ 缓存写入：                        ┃
    ┃  trip_cache.set(cache_key,        ┃
    ┃                trip_plan.dict())  ┃
    ┗━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━┛
                   │
                   ▼
         ┌─────────────────────┐
         │   前端接收 SSE       │
         │   & 显示最终行程     │
         └─────────────────────┘
```

---

## 三、逐步数据流细化

### 阶段 1：初始化 & 输入准备
```python
# 来源：backend/app/agents/trip_planner_agent.py:492–502

initial_state: PlannerState = {
    "request": request,                    # TripRequest 对象
    "cities": cities,                      # List[str]，目的地城市列表
    "primary_city": primary_city,          # str，主要城市（用于坐标修正）
    "attraction_response": "",             # str，待填充
    "weather_response": "",                # str，待填充
    "hotel_response": "",                  # str，待填充
    "food_response": "",                   # str，待填充
    "trip_plan": None,                     # Optional[TripPlan]，待填充
    "error": None,                         # Optional[str]，待填充
}
```

**关键点**：
- `request` 包含用户输入的完整信息（城市、日期、预算、偏好等）
- `cities` 支持多城市模式（会在 planner_query 中自动分配每个城市的天数）
- 四个 response 字段作为 gather 阶段的输出容器

---

### 阶段 2：gather 节点 — 并发获取信息

#### 2.1 查询构造
```python
# 来源：backend/app/agents/trip_planner_agent.py:315–321

food_pref = "、".join(request.preferences) if request.preferences else "特色"
hotel_query = f"请搜索{primary_city}的{request.accommodation}酒店"
food_query = f"请搜索{primary_city}的{food_pref}美食餐厅"

attraction_queries: List[str] = []
weather_queries: List[str] = []
for city in cities[:3]:
    pref_kw = request.preferences[0] if request.preferences else "景点"
    attraction_queries.append(f"请搜索{city}的{pref_kw}相关景点...")
    weather_queries.append(f"请查询{city}的天气信息...")
```

**关键点**：
- 根据 `request.preferences` 和 `request.accommodation` 动态构建查询
- 支持多城市，最多查询前 3 个城市的信息
- 每个查询文本传给对应 Agent（含系统提示词）

#### 2.2 并发执行与容错
```python
# 来源：backend/app/agents/trip_planner_agent.py:333–372

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
```

**关键点**：
- 使用 `asyncio.gather(..., return_exceptions=True)` 实现并发且容错
- 任意一个 Agent 调用失败不阻塞其他任务
- 异常被包装成友好文本（如 `"暂无景点数据"`）继续传递

#### 2.3 结果聚合与写回 PlannerState
```python
# 来源：backend/app/agents/trip_planner_agent.py:341–372

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

# 返回字典，更新 PlannerState
return {
    "attraction_response": attraction_response,
    "weather_response": weather_response,
    "hotel_response": _safe(hotel_result, "酒店"),
    "food_response": _safe(food_result, "餐饮"),
}
```

**关键点**：
- 结果按索引分离，对应四种类型的响应
- 多城市时，按城市标签分组聚合响应文本
- 返回字典自动更新 PlannerState 的对应字段

---

### 阶段 3：plan 节点 — LLM 汇总与 JSON 生成

#### 3.1 构建 Planner 查询
```python
# 来源：backend/app/agents/trip_planner_agent.py:377–385

planner_query = self._build_planner_query(
    request,
    state["attraction_response"],
    state["weather_response"],
    state["hotel_response"],
    state["food_response"],
    cities=state["cities"],
)
```

**关键点**：
- 将四个 response 字段直接传入 planner_query 构建函数
- 支持多城市，自动计算每个城市分配的天数
- 融入预算限制、住宿偏好等上下文信息

#### 3.2 LLM 调用与结果解析
```python
# 来源：backend/app/agents/trip_planner_agent.py:386–401

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
```

**关键点**：
- 使用 `_invoke_with_retry` 包装，支持重试与限流
- 调用 Planner LLM（`PLANNER_AGENT_PROMPT` 指定输出格式为 JSON）
- 调用 `_parse_response()` 多策略提取和解析 JSON
- 异常时返回 error 字段

#### 3.3 JSON 提取与字段校验
```python
# 来源：backend/app/agents/trip_planner_agent.py:743–782

def _extract_json_str(text: str) -> str:
    """从文本中尽力提取 JSON 字符串"""
    # 策略1：```json ... ``` 代码块
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()

    # 策略2：普通 ``` ... ``` 代码块
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            candidate = text[start:end].strip()
            if candidate.startswith("{"):
                return candidate

    # 策略3：直接找最外层 { ... }
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
    trip_plan = TripPlan.model_validate(data)  # Pydantic v2 字段校验
    logger.success("✅ planner 响应 JSON 解析成功")
    return trip_plan
except Exception as e:
    logger.warning(f"⚠️  解析响应失败，使用备用方案")
    return self._create_fallback_plan(request)
```

**关键点**：
- **多策略 JSON 提取**：处理 LLM 生成的各种不规范格式
- **Pydantic 字段校验**：
  - `accommodation` 字段支持 dict/None/str 多类型转换
  - `day_temp`/`night_temp` 支持温度字符串（"25°C"）转数字
  - `estimated_cost` 自动类型转换
- **降级机制**：解析失败时调用 `_create_fallback_plan()` 返回备用行程

---

### 阶段 4：postprocess 节点 — 后处理增强

#### 4.1 三大处理步骤
```python
# 来源：backend/app/agents/trip_planner_agent.py:403–414

def _postprocess_node(self, state: "PlannerState") -> dict:
    trip_plan: Optional[TripPlan] = state.get("trip_plan")
    if not trip_plan:
        return {"trip_plan": None, "error": state.get("error", "行程规划失败")}

    primary_city = state["primary_city"]
    self._fix_coordinates(trip_plan, primary_city)      # 步骤1：坐标修正
    self._add_weather_warnings(trip_plan)               # 步骤2：天气预警
    self._enrich_opening_hours(trip_plan, primary_city) # 步骤3：开放时间
    logger.success("✅ postprocess 节点完成")
    return {"trip_plan": trip_plan, "error": None}
```

#### 4.2 坐标修正（_fix_coordinates）
```python
# 来源：backend/app/agents/trip_planner_agent.py:552–571

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
```

**关键点**：
- 遍历所有 days → attractions，逐个调用高德地理编码 API
- 将 LLM 生成的"幻觉坐标"替换为真实坐标
- 失败时保留原坐标，不中断流程

#### 4.3 天气预警（_add_weather_warnings）
```python
# 来源：backend/app/agents/trip_planner_agent.py:572–606

def _add_weather_warnings(self, trip_plan: TripPlan) -> None:
    extreme_keywords = ["暴雨", "大暴雨", "台风", "暴雪", "冰雹", "龙卷风"]
    HIGH_TEMP = 35   # °C
    LOW_TEMP = -10   # °C

    for weather in trip_plan.weather_info:
        warnings: List[str] = []

        # 检查极端天气关键词
        combined_weather = (weather.day_weather or "") + " " + (weather.night_weather or "")
        for kw in extreme_keywords:
            if kw in combined_weather:
                warnings.append(f"⚠️ {kw}预警")
                break

        # 高温 / 严寒预警
        try:
            temp = int(weather.day_temp) if isinstance(weather.day_temp, str) else weather.day_temp
            if temp > HIGH_TEMP:
                warnings.append(f"🌡️ 高温预警（{temp}°C）")
            elif temp < LOW_TEMP:
                warnings.append(f"❄️ 严寒预警（{temp}°C）")
        except (ValueError, TypeError):
            pass

        # 大风预警（≥7级）
        m = re.search(r"(\d+)", str(weather.wind_power or ""))
        if m and int(m.group(1)) >= 7:
            warnings.append(f"💨 大风预警（{weather.wind_power}）")

        if warnings:
            weather.weather_warning = "；".join(warnings)
            logger.warning(f"🚨 {weather.date} 天气预警: {weather.weather_warning}")
```

**关键点**：
- 检测极端天气关键词、高温/严寒、大风等条件
- 将预警标签写入 `weather.weather_warning` 字段
- 前端展示时可直接使用该字段进行告警提示

#### 4.4 开放时间 enrichment（_enrich_opening_hours）
```python
# 来源：backend/app/agents/trip_planner_agent.py:607–633

def _enrich_opening_hours(self, trip_plan: TripPlan, city: str) -> None:
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
                    opentime = biz.get("opentime") or poi.get("business_area") or ""
                    if opentime:
                        attraction.opening_hours = opentime
                        logger.debug(f"🕐 {attraction.name} 开放时间: {opentime}")
            except Exception as e:
                logger.debug(f"获取开放时间失败 [{attraction.name}]: {e}")
```

**关键点**：
- 调用高德 Place Search API 获取景点实时开放时间
- 对应高德返回的 `biz_ext.opentime` 字段
- 失败时保持原有信息，不中断流程

---

### 阶段 5：SSE 流式输出与缓存

#### 5.1 缓存命中快速返回
```python
# 来源：backend/app/agents/trip_planner_agent.py:470–486

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
```

**关键点**：
- `make_trip_cache_key()` 对所有请求参数做 MD5 哈希，确保参数变化会产生不同的 key
- 命中缓存时直接跳过整个 gather/plan/postprocess 流程
- 缓存命中的响应时间从数秒降低到毫秒级

#### 5.2 LangGraph 流式执行与事件转换
```python
# 来源：backend/app/agents/trip_planner_agent.py:508–527

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
                logger.warning(f"⚠️ 上游模型临时不可用，返回备用行程: {err_msg}")
                yield {
                    "type": "progress",
                    "percent": 100,
                    "message": "⚠️ 模型服务暂时拥堵，已返回备用行程",
                }
            else:
                yield {"type": "error", "message": err_msg}
            yield {"type": "done", "data": fallback.model_dump()}
```

**关键点**：
- LangGraph `astream(stream_mode="updates")` 逐节点返回更新
- 各阶段对应不同的进度百分比和消息提示
- postprocess 完成后立即写入缓存
- 成功/失败都会 yield `done` 事件，确保前端收到最终结果

---

## 四、关键字段对照表

| 字段名 | 类型 | 来源 | 目的地 | 说明 |
|--------|------|------|--------|------|
| `request` | TripRequest | 输入 | 全流程 | 用户输入的完整请求信息 |
| `cities` | List[str] | 初始化 | gather/plan | 目的地城市列表 |
| `primary_city` | str | 初始化 | postprocess | 主要城市（用于坐标修正） |
| `attraction_response` | str | gather 输出 | plan 输入 | 景点搜索结果（文本） |
| `weather_response` | str | gather 输出 | plan 输入 | 天气查询结果（文本） |
| `hotel_response` | str | gather 输出 | plan 输入 | 酒店搜索结果（文本） |
| `food_response` | str | gather 输出 | plan 输入 | 餐饮搜索结果（文本） |
| `trip_plan` | TripPlan / None | plan 输出 | postprocess → SSE | 结构化的行程计划 JSON |
| `error` | str / None | plan 输出 | 错误处理 | 错误信息（成功为 None） |

---

## 五、代码位置导航

### PlannerState 与初始化
- **定义**：`backend/app/agents/trip_planner_agent.py:122–133`
- **初始化**：`backend/app/agents/trip_planner_agent.py:492–502`

### gather 节点
- **查询构造**：`backend/app/agents/trip_planner_agent.py:315–321`
- **Agent 创建**：`backend/app/agents/trip_planner_agent.py:223–243`
- **并发执行与聚合**：`backend/app/agents/trip_planner_agent.py:333–372`
- **异常容错机制**：`backend/app/agents/trip_planner_agent.py:347–351`

### plan 节点
- **planner_query 构建**：`backend/app/agents/trip_planner_agent.py:377–385`
- **LLM 调用与解析**：`backend/app/agents/trip_planner_agent.py:386–401`
- **JSON 提取策略**：`backend/app/agents/trip_planner_agent.py:743–770`
- **字段校验**：`backend/app/models/schemas.py`（Pydantic model_validate）

### postprocess 节点
- **整体入口**：`backend/app/agents/trip_planner_agent.py:403–414`
- **坐标修正**：`backend/app/agents/trip_planner_agent.py:552–571`
- **天气预警**：`backend/app/agents/trip_planner_agent.py:572–606`
- **开放时间**：`backend/app/agents/trip_planner_agent.py:607–633`

### SSE 与缓存
- **plan_trip_stream 入口**：`backend/app/agents/trip_planner_agent.py:460–550`
- **缓存命中检查**：`backend/app/agents/trip_planner_agent.py:470–486`
- **LangGraph 流式执行**：`backend/app/agents/trip_planner_agent.py:508–527`
- **缓存写入**：`backend/app/agents/trip_planner_agent.py:524–527`

### 容错与重试
- **重试机制**：`backend/app/agents/trip_planner_agent.py:272–289`
- **重试判定**：`backend/app/agents/trip_planner_agent.py:259–271`
- **备用方案**：`backend/app/agents/trip_planner_agent.py:784–896`

### 工具与 API
- **AMap 工具工厂**：`backend/app/agents/trip_planner_agent.py:135–199`
- **高德地理编码**：`backend/app/agents/trip_planner_agent.py:559–567`
- **高德天气查询**：`backend/app/agents/trip_planner_agent.py:165–187`
- **高德 POI 搜索**：`backend/app/agents/trip_planner_agent.py:140–163`

---

## 六、容错与鲁棒性设计

### 并发容错（gather 节点）
```python
asyncio.gather(*all_tasks, return_exceptions=True)
```
- **机制**：`return_exceptions=True` 不让异常冒泡，异常对象直接进入结果列表
- **消费**：`_safe(r, label)` 函数检测异常并转成友好文本

### LLM 调用重试（plan 节点）
```python
async def _invoke_with_retry(self, coro_factory, label: str):
    # 最多重试 3 次，指数退避（0.8s, 1.6s, 3.2s）
    # Semaphore(2) 限流
```
- **重试条件**：502/503/504、timeout、rate-limit 等
- **退避策略**：`0.8 * (2 ** attempt)` + 随机抖动

### JSON 解析降级（plan 节点）
- **策略1**：```json ... ``` 代码块提取
- **策略2**：普通 ``` ... ``` 代码块提取
- **策略3**：直接找最外层 { }
- **降级**：所有策略失败时调用 `_create_fallback_plan()`

### 后处理异常处理（postprocess 节点）
- 坐标修正失败：保留原坐标，记日志
- 天气预警失败：异常被 try/except 吃掉，不中断
- 开放时间失败：异常被捕获，保留原值

### 缓存与降级
- 缓存命中：秒级响应，完全跳过 gather/plan/postprocess
- 模型临时故障：返回备用行程（城市模板 + 占位符景点）

---

## 七、面试常见问法与核心答题点

### Q1：各 Agent 通过什么机制传递数据？
**答**：LangGraph 的 PlannerState（TypedDict），一个共享状态字典，各节点通过读/写其字段进行数据传递。

**核心字段**：request、cities、attraction/weather/hotel/food_response、trip_plan、error

**代码定位**：`backend/app/agents/trip_planner_agent.py:122–133`

---

### Q2：gather 节点如何实现四路并发？
**答**：`asyncio.gather(*all_tasks, return_exceptions=True)`

**关键点**：
- 并发（非并行），同时发起四个 I/O 请求，避免阻塞
- `return_exceptions=True` 确保任意一个失败不影响其他
- 结果通过 `_safe()` 包装处理异常，降级为文本

**代码定位**：`backend/app/agents/trip_planner_agent.py:333–372`

---

### Q3：plan 节点如何处理 LLM 的不规范 JSON 输出？
**答**：多策略 JSON 提取 + Pydantic 字段校验

**提取策略**：
1. ```json ... ``` 代码块
2. 普通 ``` ... ``` 代码块
3. 直接找最外层 { }

**字段校验**：Pydantic `model_validate` 处理：
- accommodation：dict/None/str 兼容转换
- 温度：字符串 "25°C" → 数字 25
- estimated_cost：自动类型转换

**降级**：所有失败时返回 `_create_fallback_plan()`

**代码定位**：`backend/app/agents/trip_planner_agent.py:743–782`

---

### Q4：postprocess 节点的三大处理是什么？
**答**：
1. **_fix_coordinates**：调用高德地理编码 API，将 LLM 生成的"幻觉坐标"替换为真实坐标
2. **_add_weather_warnings**：检测极端天气（暴雨/台风等）、高温/严寒、大风，写入预警标签
3. **_enrich_opening_hours**：调用高德 POI 查询，获取实时开放时间

**代码定位**：`backend/app/agents/trip_planner_agent.py:552–633`

---

### Q5：SSE 流式输出与缓存如何协调？
**答**：
- **缓存检查**（开始）：命中则直接 yield done 事件并返回，跳过整个 gather/plan/postprocess
- **缓存写入**（结束）：postprocess 完成后，在 yield done 前写入 trip_cache
- **缓存 key**：由所有请求参数 MD5 哈希生成，参数变化 key 变化

**代码定位**：`backend/app/agents/trip_planner_agent.py:470–486, 524–527`

---

### Q6：如果一个 Agent 调用失败会怎样？
**答**：
1. `asyncio.gather(return_exceptions=True)` 捕获异常，不中断其他任务
2. 异常被 `_safe()` 包装成 `"暂无XXX数据"`
3. Plan 节点继续处理，用其他三个 Agent 的数据尽力生成行程
4. 最坏情况下返回备用行程（城市模板 + 占位符景点）

**代码定位**：`backend/app/agents/trip_planner_agent.py:347–351, 784–896`

---

## 八、快速要点总结

### 数据流三大阶段
| 阶段 | 输入 | 处理 | 输出 |
|------|------|------|------|
| **gather** | request + cities | 并发调用四个 Agent | attraction/weather/hotel/food_response |
| **plan** | 四个 response | Planner LLM 汇总 | trip_plan（JSON） |
| **postprocess** | trip_plan | 坐标修正、天气预警、开放时间 | 增强后的 trip_plan |

### 并发与容错
- **并发机制**：asyncio.gather(..., return_exceptions=True)
- **降级策略**：异常 → 友好文本 → 继续处理
- **重试机制**：_invoke_with_retry + Semaphore(2) 限流
- **缓存策略**：L1 TTLCache(1hr) + 7day 分享链接 + 本地 localStorage

### 关键设计原则
- **无单点故障**：任何一个 Agent 失败不影响整体
- **鲁棒解析**：多策略 JSON 提取 + Pydantic 字段校验
- **渐进式增强**：postprocess 逐步完善坐标、预警、开放时间
- **秒级响应**：缓存命中时完全跳过计算流程

---

## 九、推荐阅读顺序

1. **快速入门**：阅读本文 Section 一、二（10 分钟）
2. **深度理解**：阅读 Section 三（逐步数据流细化）（20 分钟）
3. **代码定位**：使用 Section 五（代码位置导航）快速跳转源码（按需）
4. **面试准备**：反复阅读 Section 七（常见问法）和 Section 八（快速要点）

---

## 十、文件快速导航

| 组件 | 文件路径 | 关键行号 |
|------|---------|---------|
| LangGraph 主图 | `backend/app/agents/trip_planner_agent.py` | 293–303 |
| PlannerState 定义 | `backend/app/agents/trip_planner_agent.py` | 122–133 |
| gather 节点 | `backend/app/agents/trip_planner_agent.py` | 305–372 |
| plan 节点 | `backend/app/agents/trip_planner_agent.py` | 374–401 |
| postprocess 节点 | `backend/app/agents/trip_planner_agent.py` | 403–414 |
| SSE 流式输出 | `backend/app/agents/trip_planner_agent.py` | 460–550 |
| 数据模型 | `backend/app/models/schemas.py` | - |
| 缓存服务 | `backend/app/services/cache_service.py` | - |
| LLM 服务 | `backend/app/services/llm_service.py` | - |

---

**版本**：v1.0 | **更新时间**：2026-03-27
