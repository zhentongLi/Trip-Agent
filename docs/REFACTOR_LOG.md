# Trip-Agent 重构日志

> 记录已完成的架构优化和待执行的升级计划。

---

## 已完成：Phase 1 安全加固

**Commit:** `fa9eebf`
**分支:** `main`
**日期:** 2026-04-10

---

### S1 — JWT Secret 管理 + Fail-fast 启动校验

**背景：** 原代码在未设置 `JWT_SECRET_KEY` 时以 `secrets.token_hex(32)` 随机生成密钥，每次重启均使全部 token 失效；密钥也未纳入统一配置管理。

**变更：**

- `config.py`：
  - 新增 `jwt_secret_key: str = Field(default="")` 和 `jwt_expire_days: int = Field(default=7)` 字段
  - 将旧式 `class Config:` 内嵌类替换为 Pydantic v2 `model_config = ConfigDict(...)`（同时完成 Q5）
  - `validate_config()` 新增 JWT_SECRET_KEY 缺失时的 fail-fast 校验，启动即报错
- `auth_service.py`：
  - 删除 `_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))` 随机回退逻辑
  - 删除 `_ACCESS_TOKEN_EXPIRE_DAYS` 模块级常量
  - `create_access_token()` 和 `decode_token()` 改为调用 `get_settings()` 读取配置
  - 有效期默认从 30 天降至 7 天

---

### S2 — Auth 端点速率限制

**背景：** `/register` 和 `/login` 端点无任何速率限制，暴力枚举密码无障碍。

**变更：**

- `routes/auth.py`：
  - 引入 `from ...api.rate_limit import limiter`
  - `/register`：添加 `@limiter.limit("5/minute")`，handler 第一个参数加 `request: Request`
  - `/login`：添加 `@limiter.limit("10/minute")`，同上

> slowapi 要求：`@limiter.limit()` 必须置于 `@router.post()` **上方**，handler 的第一个参数必须是 `request: Request`。

---

## 已完成：Phase 2 性能提升

**Commit:** `fa9eebf`
**分支:** `main`
**日期:** 2026-04-10

---

### P1 — postprocess 节点并发化

**背景：** 后处理阶段 `_fix_coordinates` 和 `_enrich_opening_hours` 对每个景点逐个串行调用高德 API，10 个景点约增加 30–60s 响应时间。

**变更：**

- `services/amap_rest_client.py`：
  - 新增 `get_opening_hours_async(name, city)` — 内部复用 `_get_async()` + `asyncio.to_thread`
- `agents/nodes.py`：
  - `def postprocess(...)` → `async def postprocess(...)`
  - 新增 `async def _fix_coordinates_async(...)` — `asyncio.gather()` 并发所有景点的 geocode
  - 新增 `async def _enrich_opening_hours_async(...)` — 同理并发获取开放时间
  - `postprocess` 内部改为 `await asyncio.gather(_fix_coordinates_async, _enrich_opening_hours_async)`
  - 保留原同步方法 `_fix_coordinates` / `_enrich_opening_hours` 供测试使用

---

### P2 — PDF 生成异步化

**背景：** `generate_trip_pdf()` 是同步 ReportLab 调用，直接在 async handler 中调用会阻塞 uvicorn 事件循环。

**变更：**

- `routes/trip.py`：
  - `pdf_bytes = generate_trip_pdf(plan)` → `pdf_bytes = await asyncio.to_thread(generate_trip_pdf, plan)`

---

## 已完成：Phase 3 代码质量

**Commit:** `fa9eebf`
**分支:** `main`
**日期:** 2026-04-10

---

### Q1 — llm_service.py 全局单例清理

**背景：** Phase 4 引入 `dependencies.py` 后，`llm_service.py` 中的 `_llm_instance` 全局可变变量成为死代码冗余。

**变更：**

- `services/llm_service.py`：
  - 删除 `_llm_instance = None` 全局变量
  - 将 `get_llm()` 改为 `@lru_cache()` 装饰的工厂函数，语义等价但无可变状态
  - `reset_llm()` 改为调用 `get_llm.cache_clear()`

> 注意：`memory_service.py` 仍从 `llm_service.py` 导入 `get_llm`，避免 `dependencies.py → skills → guide_qa_skill → memory_service → dependencies` 的循环导入。

---

### Q2 — skills/router.py 全局单例清理

**背景：** `dependencies.py` 已提供 `@lru_cache get_skill_router()`，`router.py` 中的 `_router_instance` 和 `get_skill_router()` 成为冗余。

**变更：**

- `skills/router.py`：删除 `_router_instance` 和 `get_skill_router()` 函数
- `skills/__init__.py`：移除 `get_skill_router` 的 re-export
- `tests/validate_skill_flow.py`：将 `from app.skills.router import get_skill_router` 改为 `from app.dependencies import get_skill_router`

---

### Q3 — 前端 console.log 条件化

**背景：** axios 拦截器中的 `console.log` / `console.error` 在生产构建中仍会输出，泄露请求细节。

**变更：**

- `frontend/src/services/api.ts`：所有拦截器中的日志调用改为 `if (import.meta.env.DEV) { ... }` 条件输出

---

### Q4 — TypeScript error: unknown 收窄

**背景：** `api.ts` 中多处 `catch (error: any)` 绕过了 TypeScript 类型检查，可能掩盖运行时错误。

**变更：**

- `frontend/src/services/api.ts`：
  - 所有 `catch (error: any)` 改为 `catch (error: unknown)`
  - 使用 `axios.isAxiosError(error)` 分支处理 HTTP 错误
  - 使用 `error instanceof Error` 分支处理通用错误

---

### Q5 — Pydantic v2 ConfigDict（同 S1 一并完成）

- `config.py`：`class Config:` 内嵌类替换为 `model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")`

---

## 已完成：Phase 4 架构重构

**Commit:** `35e83fa`
**分支:** `main`
**日期:** 2026-04-09

---

### 1. 拆分 `agents/trip_planner_agent.py`（1025 行单文件 → 6 个模块）

**背景：** 原文件将 Agent 提示词、状态定义、工具工厂、LangGraph 节点、JSON 解析、Planner 编排全部耦合，难以测试和维护。

| 新文件 | 行数 | 职责 |
|--------|------|------|
| `agents/prompts.py` | ~100 | 5 个 Agent 系统提示词常量 |
| `agents/state.py` | ~15 | `PlannerState` TypedDict |
| `agents/tools.py` | ~45 | `make_amap_tools(client)` 工厂 |
| `agents/parsers.py` | ~70 | `extract_json_str` / `parse_trip_response` / `parse_adjust_response`，消除原文件中重复的 JSON 提取逻辑 |
| `agents/nodes.py` | ~200 | `NodeFactory`（gather / plan / postprocess 三个 LangGraph 节点）|
| `agents/planner.py` | ~280 | `MultiAgentTripPlanner` 精简编排器，对外接口不变 |
| `agents/trip_planner_agent.py` | 15 | 兼容垫片，不包含任何业务逻辑 |

---

### 2. FastAPI 依赖注入（`app/dependencies.py`）

**背景：** 原代码通过全局 `_xxx = None` + `get_xxx()` 单例函数提供服务实例，测试时只能用 `monkeypatch.setattr` 替换，且各服务的构建顺序隐含在各自模块中。

**变更：**
- 新建 `app/dependencies.py`，集中定义所有 `@lru_cache` 工厂：
  - `get_llm()` — ChatOpenAI 实例
  - `get_amap_client()` — AmapRestClient（含熔断器）
  - `get_trip_planner()` — MultiAgentTripPlanner
  - `get_trip_cache()` — TTLCache（TTL=1h）
  - `get_share_store()` — ShareStore
  - `get_skill_router()` — SkillRouter（含 GuideQASkill）
- `routes/trip.py`、`routes/guide.py` 全部改为 `Depends(get_xxx)`，消除路由层全局单例调用。
- 测试层改用 `app.dependency_overrides` 注入 FakePlanner，新增 `client_with_mock_planner` fixture。

---

### 3. AMap 熔断器（`services/circuit_breaker.py` + `services/amap_rest_client.py`）

**背景：** 原代码有 5 处内联 `requests.get` 直接调用高德 REST API，无任何熔断或限流保护，AMap 宕机时请求会无限等待直到超时。

**变更：**
- `services/circuit_breaker.py`：通用线程安全熔断器，状态机 CLOSED → OPEN → HALF_OPEN。
  - 默认参数：5 次连续失败后开路，30s 后尝试半开。
  - 支持同步 `call()` 和异步 `call_async()` 两种调用方式。
- `services/amap_rest_client.py`：将 5 处 `requests.get` 统一封装为 `AmapRestClient`：
  - `search_places()` / `search_places_async()`
  - `get_weather()` / `get_weather_async()`
  - `geocode()` / `geocode_async()`
  - `get_opening_hours()` / `get_opening_hours_async()`
  - 所有方法经熔断器保护，含 1 次自动重试（0.5s 间隔）。

---

### 4. 集中式错误处理层（`app/errors/`）

**背景：** 原代码错误处理散落在各路由的 `try/except HTTPException`，缺乏统一的响应结构和可机器解析的 `error_code`。

**变更：**
- `errors/types.py`：异常层次结构
  ```
  AppError
  ├── ExternalServiceError
  │   └── CircuitOpenError    (HTTP 503, error_code: CIRCUIT_OPEN)
  ├── PlanningError           (HTTP 500, error_code: PLANNING_FAILED)
  ├── ValidationError         (HTTP 400, error_code: VALIDATION_ERROR)
  ├── NotFoundError           (HTTP 404, error_code: NOT_FOUND)
  ├── AuthenticationError     (HTTP 401, error_code: AUTHENTICATION_ERROR)
  └── RateLimitError          (HTTP 429, error_code: RATE_LIMIT_EXCEEDED)
  ```
- `errors/schemas.py`：统一 `ErrorResponse(success, error_code, message, details)` 响应包。
- `errors/handlers.py`：`register_error_handlers(app)` 一次性注册到 FastAPI，覆盖 `AppError`、`RequestValidationError`、兜底 `Exception`。

---

### 5. 测试更新（Phase 4）

- `conftest.py`：新增 `client_with_mock_planner` async fixture，通过 `dependency_overrides` 注入 `FakePlanner`，测试结束后自动清理。
- `test_routes.py`：`test_adjust_with_valid_payload_calls_agent` 从 `monkeypatch.setattr` 迁移到新 fixture。
- **验证：31/31 测试全部通过。**

---

## 待升级优化列表

### 🔴 严重（安全）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| S1 | ✅ 已完成 | **JWT Secret 每次重启失效** | `validate_config()` fail-fast + `config.py` 统一管理 |
| S2 | ✅ 已完成 | **Auth 端点无速率限制** | `/register` 5/min · `/login` 10/min |
| S3 | ⬜ 待做 | **JWT Token 有效期长，无刷新机制** — 已从 30 天降至 7 天，但无 refresh token | 实现 refresh token 接口（较复杂，后续迭代） |

### 🟠 高（性能）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| P1 | ✅ 已完成 | **后处理节点串行 API 调用** | `postprocess` 改为 async + `asyncio.gather()` 并发 |
| P2 | ✅ 已完成 | **PDF 生成阻塞事件循环** | `asyncio.to_thread(generate_trip_pdf, plan)` |
| P3 | ⬜ 待做 | **RAG Cross-Encoder 每次查询重新推理** | 按查询 hash 缓存 reranking 结果 |

### 🟠 高（测试）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| T1 | ⬜ 待做 | **前端零测试覆盖** | 为 `api.ts`、`Home.vue`、`Result.vue` 添加 Vitest 单元测试 |
| T2 | ⬜ 待做 | **无 E2E 测试** | Playwright 覆盖：规划→展示→导出核心路径 |
| T3 | ⬜ 待做 | **无数据库集成测试** | Auth 路由 + 真实 SQLite + 事务回滚 fixture |

### 🟡 中（缓存与隔离）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| C1 | ⬜ 待做 | **Cache 无用户隔离** | cache key 加入 `user_id`（已登录时）|
| C2 | ⬜ 待做 | **`ShareStore` 无持久化** | 持久化到 SQLite 或 Redis |

### 🟡 中（代码质量）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| Q1 | ✅ 已完成 | **`llm_service.py` 全局单例** | 改为 `@lru_cache`，消除可变状态 |
| Q2 | ✅ 已完成 | **`skills/router.py` 全局单例** | 删除 `_router_instance`，统一走 `dependencies.py` |
| Q3 | ✅ 已完成 | **前端 `console.log` 在生产拦截器** | `import.meta.env.DEV` 条件包裹 |
| Q4 | ✅ 已完成 | **TypeScript `error: any`** | 改为 `unknown` + `axios.isAxiosError()` 收窄 |
| Q5 | ✅ 已完成 | **`config.py` 旧式 `class Config`** | 改为 `model_config = ConfigDict(...)` |

### 🟡 中（功能完善）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| F1 | ⬜ 待做 | **多城市路线规划不完整** | 集成 AMap 路线规划 API 计算城际交通 |
| F2 | ⬜ 待做 | **预算约束无后处理验证** | 后处理阶段验证总费用并触发二次调整 |
| F3 | ⬜ 待做 | **天气预警无动作** | 极端天气日自动建议室内景点备选 |

### 🔵 低（DevOps）

| # | 状态 | 问题 | 修复方案 |
|---|------|------|----------|
| D1 | ⬜ 待做 | **Docker 无 HTTPS** | nginx + SSL 终止层 |
| D2 | ⬜ 待做 | **Docker 无资源限制** | `deploy.resources.limits` |
| D3 | ⬜ 待做 | **requirements.txt 无开发依赖分离** | 拆分 `requirements-dev.txt` |
| D4 | ⬜ 待做 | **`on_event` 已废弃** | 迁移到 `@asynccontextmanager lifespan` |

---

## 优化路线总览

| 阶段 | 状态 | 重点 | 收益 |
|------|------|------|------|
| **Phase 4** | ✅ 已完成（2026-04-09）| 模块拆分、依赖注入、熔断器、错误处理 | 可维护性、可测试性显著提升 |
| **Phase 1** | ✅ 已完成（2026-04-10）| S1 JWT 修复、S2 Auth 限流、P1 后处理并发、P2 PDF 异步、Q1-Q5 代码质量 | 安全加固 + 性能提升 30-60s |
| **Phase 2** | ⬜ 待做 | T1 前端单测、T2 E2E、T3 DB 集成测试 | 回归覆盖率 ≥ 80% |
| **Phase 3** | ⬜ 待做 | S3 Refresh Token、P3 RAG 缓存、C1/C2 缓存隔离、F1-F3 功能完善 | 生产就绪 |
