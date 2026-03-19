# HelloAgents 智能旅行规划平台

基于 HelloAgents + FastAPI + Vue3 的全栈 AI 项目，支持多智能体并行规划、SSE 流式进度、导游 RAG 问答、行程分享、PDF 导出、用户登录与云端行程存储。

## 项目亮点

- 5-Agent 并行编排：景点、天气、酒店、餐饮并行采集，规划 Agent 统一整合。
- MCP 工具集成：通过 `amap-mcp-server` 接入高德地图工具链（stdio 传输）。
- SSE 流式体验：前端实时展示进度（开始 -> 搜索 -> 规划 -> 后处理 -> 完成）。
- 多城市联游：支持输入城市链路（如北京->西安->成都）并按天数自动分配。
- 预算约束与天气预警：预算上限注入规划，自动标记极端天气风险。
- LLM 容错链路：多格式 JSON 提取 + Pydantic 校验 + fallback 兜底。
- 导游 RAG 模式：本地知识库检索 + LLM 生成，支持携带当前行程上下文。
- 用户系统：JWT 登录注册 + SQLite 持久化云端行程。
- 实用功能：AI 行程调整、分享链接（7天 TTL）、后端 PDF 导出。

## 技术栈

后端
- FastAPI
- HelloAgents (`SimpleAgent`, `HelloAgentsLLM`)
- MCPTool + amap-mcp-server
- Pydantic v2 / pydantic-settings
- SQLModel + SQLite
- Loguru

前端
- Vue 3 + TypeScript + Vite
- Ant Design Vue
- Axios + Fetch Stream
- 高德地图 JS API 2.0
- html2canvas + jsPDF

## 核心架构

```text
Home 表单 -> POST /api/trip/plan/stream (SSE)
               -> MultiAgentTripPlanner.plan_trip_stream()
                   -> 缓存检查
                   -> 并行执行 4 个采集 Agent
                   -> Planner Agent 汇总
                   -> 坐标修正 / 天气预警 / 开放时间补充
                   -> 写入缓存并流式返回
               -> Result 页面渲染地图、预算、天气、行程
```

## 目录结构

```text
helloagents-trip-planner/
├── backend/
│   ├── app/
│   │   ├── agents/trip_planner_agent.py
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   └── routes/
│   │   │       ├── trip.py
│   │   │       ├── guide.py
│   │   │       ├── auth.py
│   │   │       ├── user.py
│   │   │       ├── share.py
│   │   │       ├── map.py
│   │   │       └── poi.py
│   │   ├── models/
│   │   ├── services/
│   │   └── config.py
│   ├── data/
│   │   └── guide_knowledge.json
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/Home.vue
│   │   ├── views/Result.vue
│   │   └── services/
│   └── package.json
├── docker-compose.yml
├── start.sh
└── README.md
```

## 运行环境

- Python 3.12（推荐使用 Conda 环境 `trip-agent`）
- Node.js 20+
- npm 10+
- 高德 API Key（后端 Web Service + 前端 JS Key + Security Code）
- LLM API（兼容 OpenAI SDK）

## 环境变量配置

后端 `backend/.env` 至少包含：

```env
AMAP_API_KEY=你的高德Web服务Key
LLM_API_KEY=你的模型服务Key
LLM_BASE_URL=https://你的兼容OpenAI地址/v1
LLM_MODEL_ID=gpt-4.1-nano

HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 可选
JWT_SECRET_KEY=建议生产环境设置
JWT_EXPIRE_DAYS=30
UNSPLASH_ACCESS_KEY=
UNSPLASH_SECRET_KEY=
```

前端 `frontend/.env` 示例：

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
- 前端：http://localhost:5173
- 后端文档：http://localhost:8000/docs

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

## API 总览

主要业务接口（前缀均为 `/api`）：

- 旅行规划
   - `POST /trip/plan/stream`：SSE 流式生成行程
   - `POST /trip/plan`：JSON 一次性返回
   - `POST /trip/adjust`：AI 自然语言调整行程
   - `POST /trip/export/pdf`：后端生成 PDF
   - `GET /trip/cache/stats`、`DELETE /trip/cache`
- 行程分享
   - `POST /trip/share`、`GET /trip/share/{share_id}`、`DELETE /trip/share/{share_id}`
- 导游 RAG
   - `POST /guide/ask`
- 用户与云端行程
   - `POST /auth/register`、`POST /auth/login`、`GET /auth/me`
   - `GET /user/trips`、`POST /user/trips`、`GET /user/trips/{id}`、`DELETE /user/trips/{id}`
- 地图与 POI（基础接口）
   - `GET /map/poi`、`GET /map/weather`、`POST /map/route`
   - `GET /poi/search`、`GET /poi/detail/{poi_id}`、`GET /poi/photo`

## 测试

后端测试位于 `backend/tests`，当前包含 31 个测试用例（路由、Schema、分享服务）。

```bash
cd backend
conda run -n trip-agent python -m pytest tests/ -q
```

## Docker 部署

```bash
docker-compose up --build
```

默认端口：
- 前端：80
- 后端：8000

说明：Nginx 已配置 SSE 透传（`proxy_buffering off`）。

## 常见问题

1. 8000 端口被占用

```bash
lsof -ti:8000 | xargs kill -9
```

2. 地图不显示
- 检查 `VITE_AMAP_WEB_JS_KEY` 与 `VITE_AMAP_SECURITY_CODE`。
- 确认高德控制台已配置域名白名单。

3. LLM 调用失败
- 检查 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_ID` 是否正确。
- 确认 `LLM_BASE_URL` 包含 `/v1` 路径。

4. MCP 工具未生效
- 确认环境中可执行 `uvx amap-mcp-server`。
- 首次启动可能较慢，查看后端日志 `backend/logs/startup.log`。

## 安全建议

- 不要提交包含真实密钥的 `.env` 文件。
- 生产环境请配置强随机 `JWT_SECRET_KEY`，并收紧 `CORS_ORIGINS`。

## 许可证

CC BY-NC-SA 4.0

## 致谢

- HelloAgents
- amap-mcp-server
- 高德开放平台

