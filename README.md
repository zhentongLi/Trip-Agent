# Trip-Agent 智能旅行规划平台

基于 FastAPI + Vue 3 的全栈 AI 旅行规划项目。后端采用 LangGraph 编排多智能体流程，前端通过 SSE 实时展示生成进度，支持行程生成、行程调整、导游问答、行程分享、PDF 导出与用户登录存储。

## 项目亮点

- LangGraph 工作流：按 gather -> plan -> postprocess 三阶段执行。
- 多智能体并行采集：景点、天气、酒店、餐饮并发检索。
- 高德 REST 工具链：通过结构化工具直接调用高德 API，无需 MCP 子进程。
- SSE 流式体验：前端实时显示进度和最终结果。
- 异常韧性：对 502/503/504 等上游错误做重试、限流与备用行程降级。
- 多城市联游：支持城市链路输入并自动分配天数。
- 行程可运营：AI 调整、分享链接、云端存储、PDF 导出完整闭环。

## 技术栈

后端
- FastAPI
- LangGraph + LangChain
- langchain-openai (ChatOpenAI)
- Pydantic v2 / pydantic-settings
- SQLModel + SQLite
- Loguru
- ReportLab

前端
- Vue 3 + TypeScript + Vite
- Ant Design Vue
- Axios + Fetch Stream (SSE)
- 高德地图 JS API 2.0
- html2canvas + jsPDF

## 核心流程

```text
Home 表单
   -> POST /api/trip/plan/stream (SSE)
      -> MultiAgentTripPlanner.plan_trip_stream()
         -> 缓存命中检查
         -> gather: 并行采集景点/天气/酒店/餐饮
         -> plan: LLM 整合为结构化行程
         -> postprocess: 坐标修正/天气预警/开放时间补充
         -> 写缓存并返回 done 事件
   -> Result 页面渲染地图、预算与每日安排
```

## 目录结构

```text
Trip-Agent/
├── backend/
│   ├── app/
│   │   ├── agents/trip_planner_agent.py
│   │   ├── api/main.py
│   │   ├── api/routes/
│   │   ├── models/
│   │   ├── services/
│   │   └── config.py
│   ├── data/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── start.sh
└── README.md
```

## 运行环境

- Python 3.12 (推荐 Conda 环境 trip-agent)
- Node.js 20+
- npm 10+
- 高德 API Key (后端 Web Service + 前端 JS Key + Security Code)
- 兼容 OpenAI 协议的 LLM 服务

## 环境变量

后端文件：backend/.env

```env
AMAP_API_KEY=你的高德Web服务Key

# LLM 配置 (优先读取 LLM_*，兼容 OPENAI_*)
LLM_API_KEY=你的模型服务Key
LLM_BASE_URL=https://你的兼容OpenAI地址/v1
LLM_MODEL=gpt-4.1-nano

HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 可选
JWT_SECRET_KEY=建议生产环境设置
JWT_EXPIRE_DAYS=30
UNSPLASH_ACCESS_KEY=
UNSPLASH_SECRET_KEY=
```

前端文件：frontend/.env

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_JS_KEY=你的高德JS Key
VITE_AMAP_SECURITY_CODE=你的高德Security Code
```

## 快速启动

### 方式一：一键启动（推荐）

在项目根目录执行：

```bash
bash start.sh
```

默认地址：
- 前端: http://localhost:5173
- 后端文档: http://localhost:8000/docs

### 方式二：手动启动

后端

```bash
cd backend
conda create -n trip-agent python=3.12 -y
conda activate trip-agent
pip install -r requirements.txt
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

前端

```bash
cd frontend
npm install
npm run dev
```

## API 概览

接口统一前缀：/api

- 旅行规划
   - `POST /trip/plan/stream`：SSE 流式生成行程
   - `POST /trip/plan`：JSON 一次性返回
   - `POST /trip/adjust`：AI 自然语言调整行程
   - `POST /trip/export/pdf`：后端生成 PDF
   - `GET /trip/cache/stats`、`DELETE /trip/cache`
   - `GET /trip/health`
- 行程分享
   - `POST /trip/share`、`GET /trip/share/{share_id}`、`DELETE /trip/share/{share_id}`
- 导游 RAG
   - `POST /guide/ask`
- 用户与云端行程
   - `POST /auth/register`、`POST /auth/login`、`GET /auth/me`
   - `GET /user/trips`、`POST /user/trips`、`GET /user/trips/{id}`、`DELETE /user/trips/{id}`
- 地图与 POI
   - `GET /map/poi`、`GET /map/weather`、`POST /map/route`
   - `GET /poi/search`、`GET /poi/detail/{poi_id}`、`GET /poi/photo`

## 今日更新（2026-03-22）

### 技术升级

- RAG 架构升级为向量检索：导游知识库已接入 Chroma 持久化向量库，支持远端 embedding（不可用时自动降级本地哈希向量）。
- Advanced RAG Pipeline 落地：新增 Query Rewriting（Multi-Query / Step-Back / 可选 HyDE）、Re-ranking（Cross-Encoder 优先，失败回退轻量重排）、Iterative Retrieval（信息不足时自动二次检索）。
- Runtime Skill 架构落地：新增 `RuntimeSkill`、`SkillRegistry`、`SkillRouter`，导游问答统一通过 `guide_qa` skill 分发执行。
- Memory 模块升级为多实例友好：`MemoryService` 支持 Redis 共享存储（会话短期记忆 + 用户长期画像），无 Redis 时回退本地模式。
- 可观测性增强：导游接口支持 `debug` 调试开关，返回 `skill_meta` 与 `retrieval_meta`（包含命中来源、改写查询、迭代轮次、本地知识库命中标记等）。
- 自动化验证增强：新增 `backend/tests/validate_skill_flow.py`，支持 router / api / all 多模式验证。

### 业务能力扩展

- 导游问答从“单轮回答”升级为“可解释、可追踪”的检索问答：可直接看到命中来源与检索链路。
- 增强个性化体验：导游回答可融合会话历史偏好（预算、风格、禁忌、历史目的地）进行上下文生成。
- 支持生产部署场景：记忆层支持线上多实例共享，避免多副本下会话割裂。
- 前端新增导游调试面板（仅开发环境显示）：可视化展示 Skill 命中、RAG 来源统计、改写查询、迭代轮次与重排模式。

### 验证与运行状态

- 后端健康检查、导游问答接口、行程规划接口均已实测通过。
- Skill 验证脚本（ASGI / live）已可执行，定位与规避了本地代理干扰导致的假性 502 问题。

### 运维建议

- 生产环境建议开启 Redis 并配置：`MEMORY_REDIS_URL`、`MEMORY_REDIS_NAMESPACE`、`MEMORY_SESSION_TTL_SECONDS`。
- 开发环境可开启导游调试开关进行链路排查；生产环境默认隐藏调试面板，避免暴露内部检索细节。

## 测试

```bash
cd backend
conda run -n trip-agent python -m pytest tests/ -q
```

## Docker 部署

```bash
docker compose up --build
```

默认端口：
- 前端: 80
- 后端: 8000

## 常见问题

1. 8000 端口被占用

```bash
lsof -ti:8000 | xargs kill -9
```

2. 地图不显示
- 检查前端变量 VITE_AMAP_WEB_JS_KEY 与 VITE_AMAP_SECURITY_CODE。
- 检查高德控制台域名白名单。

3. LLM 调用失败
- 检查 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL (或 OPENAI_*)。
- 确认 LLM_BASE_URL 包含 /v1。

4. 结果降级为备用行程
- 通常是上游模型网关临时拥堵，系统会自动重试并返回可用结果。
- 可在 backend/logs 里查看重试日志。

## 安全建议

- 不要提交包含真实密钥的 .env 文件。
- 若密钥疑似泄露，请立即在供应商后台轮换。
- 生产环境请设置强随机 JWT_SECRET_KEY，并收紧 CORS_ORIGINS。

## 许可证

CC BY-NC-SA 4.0


