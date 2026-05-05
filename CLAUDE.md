# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (FastAPI + LangGraph)

```bash
cd backend

# Run all tests (~98 test cases)
/opt/anaconda3/envs/trip-agent/bin/python -m pytest tests/ -q
# or with conda:
conda run -n trip-agent python -m pytest tests/ -q

# Run a single test file
conda run -n trip-agent python -m pytest tests/test_routes.py -q

# Run a single test by name
conda run -n trip-agent python -m pytest tests/test_routes.py::TestTripAdjust::test_adjust_rejects_empty_message -q

# Start development server (requires .env with JWT_SECRET_KEY)
/opt/anaconda3/envs/trip-agent/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

# RAG evaluation (requires backend/data/rag_eval_dataset.json)
conda run -n trip-agent python tests/evaluate_rag.py
conda run -n trip-agent python tests/evaluate_rag.py --k 1 3 5 10 --output results.json
```

### Frontend (Vue 3 + TypeScript + Vite)

```bash
cd frontend
npm run dev      # Development server (port 5173)
npm run build    # Production build
```

### One-Command Start / Docker

```bash
bash start.sh                 # backend :8000, frontend :5173
docker-compose up --build
```

## Backend Architecture (`backend/app/`)

### Module Map

```
app/
├── api/
│   ├── main.py          # FastAPI app init: CORS, SlowAPI, register_error_handlers()
│   │                    #   GET /health/redis — per-service Redis status check
│   ├── rate_limit.py    # limiter singleton — import from here only (avoid circular)
│   │                    #   Uses Redis storage_uri when REDIS_URL is set
│   └── routes/          # All route handlers use Depends() — no direct singleton calls
│       ├── trip.py      # /api/trip/* — injects MultiAgentTripPlanner + cache
│       ├── guide.py     # /api/guide/ask + /api/guide/skill/{poi,adjust} + GET /api/skills
│       │                #   All dispatch through SkillRouter — uniform error handling
│       ├── share.py     # Share link management — uses Depends(get_share_store) + async methods
│       ├── auth.py      # JWT auth
│       ├── user.py      # Cloud trip CRUD
│       └── map.py       # AMap POI/weather/route utilities
├── agents/              # LangGraph multi-agent system
│   ├── planner.py       # MultiAgentTripPlanner — plan_trip_stream, plan_trip, adjust_trip
│   │                    #   Two semaphores: _gather_semaphore(4) and _plan_semaphore(4)
│   │                    #   Cache read/write uses await cache.aget/aset (async-aware)
│   ├── nodes.py         # NodeFactory — gather / plan / postprocess LangGraph nodes
│   │                    #   _stream_llm_with_latency(): streams plan-phase LLM calls,
│   │                    #   logs TTFT (network queuing) and generation time separately
│   ├── preprocessor.py  # preprocess_responses(): 3-step gather output cleaning
│   │                    #   1. quality filter (_FAILURE_PATTERNS, min 20 chars)
│   │                    #   2. exact dedup (MD5 hash)
│   │                    #   3. Jaccard similarity dedup (threshold 0.85)
│   ├── token_budget.py  # allocate(total, days) → BudgetPlan(frozen dataclass)
│   │                    #   Proportional allocation by complexity weight per task type
│   │                    #   gather=0.03, day_plan=0.20, full_plan_per_day=0.28
│   ├── compressor.py    # compress_agent_responses() — rule-based (no LLM) context compression
│   │                    #   POI: ~50-55% reduction; weather: ~55-60%; overall: ~60-70%
│   ├── parsers.py       # extract_json_str, parse_trip_response, parse_adjust_response
│   ├── prompts.py       # All 5 agent system prompts
│   ├── state.py         # PlannerState TypedDict
│   ├── tools.py         # make_amap_tools(client) → (search_places_tool, get_weather_tool)
│   └── trip_planner_agent.py  # ← compatibility shim only; do not add logic here
├── dependencies.py      # ALL FastAPI Depends() factories — single source of truth
│                        #   get_sync_redis() / get_async_redis() — shared Redis clients
│                        #   get_trip_planner, get_trip_cache, get_share_store, get_skill_router
│                        #   get_amap_client — selects CircuitBreaker or RedisCircuitBreaker
├── errors/
│   ├── types.py         # Exception hierarchy: AppError → ExternalServiceError → CircuitOpenError
│   │                    #   + SkillExecutionError / SkillNotFoundError (raised by SkillRouter)
│   ├── schemas.py       # ErrorResponse Pydantic model
│   └── handlers.py      # register_error_handlers(app) — called once in main.py
├── services/
│   ├── amap_rest_client.py  # AmapRestClient: search_places, get_weather, geocode, get_opening_hours
│   ├── circuit_breaker.py   # CircuitBreaker (in-process) + RedisCircuitBreaker (distributed, opt-in)
│   │                        #   Lua atomic scripts for state transitions; enabled via CIRCUIT_BREAKER_REDIS_ENABLED=true
│   ├── cache_service.py     # TTLCache — in-memory + aget/aset async wrappers for uniform call sites
│   ├── redis_cache.py       # RedisCache — Redis String backend with TTLCache fallback
│   │                        #   Same interface as TTLCache (get/set/aget/aset); callers need not know which is active
│   ├── share_service.py     # ShareStore — Redis Hash (7-day TTL) with in-memory fallback
│   │                        #   Async: acreate/aget/adelete; Sync: create/get/delete (tests + compat)
│   ├── memory_service.py    # Two-layer memory: session (Redis List/String) + user profile (Redis Hash)
│   │                        #   async_record_turn uses Lua atomic RPUSH to prevent concurrent-write data loss
│   ├── rag_service.py       # ChromaDB + BM25 hybrid retrieval, optional CrossEncoder reranking
│   │                        #   Rerank results cached in Redis (24h TTL) via _redis_rerank_get/set
│   ├── llm_service.py       # get_llm() — kept for legacy; prefer dependencies.py
│   └── pdf_service.py       # ReportLab PDF generation
├── skills/              # Pluggable skill architecture (strategy + registry pattern)
│   ├── base.py          # RuntimeSkill ABC — name, description, run(), metadata()
│   ├── registry.py      # SkillRegistry — register / get / list_names / list_skills
│   ├── router.py        # SkillRouter.dispatch() — wraps exceptions as SkillExecutionError
│   │                    #                          raises SkillNotFoundError for unknown names
│   ├── guide_qa_skill.py    # GuideQASkill — constructor-injected rag + memory services
│   ├── poi_recommend_skill.py  # POIRecommendSkill — wraps AmapRestClient structured POI search
│   └── trip_adjust_skill.py    # TripAdjustSkill — wraps planner.adjust_trip via skill entry
├── models/
│   ├── schemas.py       # Pydantic v2: TripRequest, TripPlan, DayPlan, Attraction, Meal, …
│   └── db_models.py     # SQLModel: User, SavedTrip (SQLite)
└── config.py            # pydantic-settings Settings — includes all Redis fields with AliasChoices
```

### LangGraph Agent Flow

```
START → gather → plan → postprocess → END

gather:      NodeFactory.gather() — asyncio.gather() up to 2N+2 agents in parallel
             Attraction × N cities, Weather × N cities, Hotel, Food (max N=3)
             Output passed through preprocess_responses() before being stored in state
             _gather_semaphore(4) limits concurrent LLM slots

plan:        NodeFactory.plan() — tries parallel per-day mode first, falls back to single call
             Per-day: N tasks via asyncio.gather(), each calls _stream_llm_with_latency()
             which logs TTFT + generation time; JSON parse errors retry up to 2×
             Token budget allocated via allocate(total_budget, travel_days) → BudgetPlan
             _plan_semaphore(4) limits concurrent LLM slots
             Fallback: _plan_single_call() — one LLM call for full itinerary JSON

postprocess: NodeFactory.postprocess() — order matters:
             1. _dedup_attractions()     → cross-day exact + Jaccard dedup (before API calls)
             2. _dedup_meals()           → cross-day per-meal-type restaurant dedup
             3. _fix_coordinates_async() → AmapRestClient.geocode() (concurrent, Semaphore(5))
             4. _enrich_opening_hours()  → AmapRestClient.get_opening_hours() (concurrent)
             5. _add_weather_warnings()  → regex on weather strings
             → writes result to RedisCache / TTLCache
```

`plan_trip_stream()` accepts a `cache` parameter. Pass via `Depends(get_trip_cache)`. Cache reads/writes use `await cache.aget/aset` — both `TTLCache` and `RedisCache` implement this interface.

### Dependency Injection Pattern

All services are provided through `app/dependencies.py`. Routes **must not** call service constructors directly:

```python
# CORRECT
async def my_route(
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    cache = Depends(get_trip_cache),            # returns RedisCache or TTLCache
    store: ShareStore = Depends(get_share_store),
    user_id: int = Depends(get_current_user_id),      # forced auth (401 if missing)
    user_id: int | None = Depends(get_optional_user_id),  # optional auth (None if missing)
): ...

# WRONG
agent = get_trip_planner_agent()   # deprecated shim, raises RuntimeError
```

All factories use `@lru_cache()` for process-level singletons. Override in tests via `app.dependency_overrides`.

### Authentication

Two auth dependency factories are provided in `app/dependencies.py`:

| Factory | Behavior | Use case |
|---|---|---|
| `get_current_user_id` | Raises `AuthenticationError` (401) if no/invalid token | Protected endpoints |
| `get_optional_user_id` | Returns `None` if no/invalid token | Optional auth (anonymous allowed) |

**Route authentication matrix:**

| Route | Auth | Notes |
|---|---|---|
| `GET /auth/me`, all `/user/trips/*` | Required | `get_current_user_id` |
| `DELETE /trip/cache`, `GET /trip/cache/stats` | Required | Internal admin ops |
| `DELETE /trip/share/{id}` | Required + ownership | `acheck_owner` verifies creator_id |
| `/trip/plan`, `/trip/plan/stream`, `/trip/adjust` | Optional | Anonymous users allowed |
| `/guide/ask`, `/guide/skill/*` | Optional | Anonymous users allowed |
| `GET /trip/share/{id}`, `POST /trip/share` | Anonymous | POST records creator_id if logged in |

**Error types** (in `app/errors/types.py`):
- `AuthenticationError` → HTTP 401, `error_code="AUTHENTICATION_ERROR"`
- `AuthorizationError` → HTTP 403, `error_code="FORBIDDEN"`

**Share ownership**: `ShareStore.acreate()` accepts `creator_id: int | None`. `acheck_owner(share_id, user_id)` returns False for anonymous shares (creator_id=None) — old shares without creator cannot be deleted (expire naturally after 7 days).

### Redis Integration

All Redis usage follows the **silent fallback pattern** — any Redis error logs a warning and falls back to local state, never raising to the caller:

```python
try:
    return await self._redis_op(...)
except (RedisError, TimeoutError) as e:
    logger.warning("redis_fallback domain=%s err=%s", domain, e)
    return self._local_fallback(...)
```

**Redis key namespace** (prefix `trip_agent:` by default, configurable via `REDIS_NAMESPACE`):

| Key pattern | Type | TTL | Used by |
|---|---|---|---|
| `session:{sid}:messages` | List | 3 days | MemoryService |
| `session:{sid}:summary` | String | 3 days | MemoryService |
| `profile:{sid}` | Hash | 30 days | MemoryService |
| `trip:plan:{md5}` | String (JSON) | 1 hour | RedisCache / planner |
| `share:{id}` | Hash | 7 days | ShareStore |
| `rag:rerank:{hash}` | String (JSON) | 24 hours | GuideRAGService |
| `cb:amap` | Hash | sliding | RedisCircuitBreaker |

**`GET /health/redis`** — reports per-service Redis status (`ok` / `local_fallback` / `error`). Check this after deployment to confirm Redis connectivity.

**Emergency kill switch**: set `REDIS_DISABLE=true` to force all components to local fallback instantly.

### Mocking Services in Tests

```python
from app.api.main import app
from app.dependencies import get_trip_planner, get_trip_cache
from app.services.cache_service import TTLCache

app.dependency_overrides[get_trip_planner] = lambda: FakePlanner()
app.dependency_overrides[get_trip_cache]   = lambda: TTLCache(ttl_seconds=60)
# ... run test ...
app.dependency_overrides.pop(get_trip_planner, None)
app.dependency_overrides.pop(get_trip_cache, None)
```

The `client_with_mock_planner` fixture in `conftest.py` handles this automatically.

When mocking `NodeFactory` internals (e.g. `_stream_llm_with_latency`), assign an `AsyncMock` directly on the factory instance — do not mock `_invoke_with_retry`, which is only used by gather-phase agent calls.

### Skills System

Pluggable capability layer built on the **strategy + registry** pattern — frontend discovers skills dynamically via `GET /api/skills`, invokes them through dedicated routes.

**Adding a new skill:**

1. Subclass `RuntimeSkill` in `backend/app/skills/`, set class-level `name` + `description`, implement `async run(payload) -> dict`.
2. **Inject dependencies via constructor** — do NOT call `get_xxx()` globals inside `run()`. This keeps skills testable and preserves the DI contract.
3. Register in `dependencies.py::get_skill_router()`: `registry.register(MySkill(dep=get_some_dep()))`.
4. (Optional) Add a thin route in `guide.py` that validates request schema and dispatches via `skill_router.dispatch("my_skill", payload)`.

**Error contract:** `SkillRouter.dispatch()` catches all exceptions from `skill.run()` and wraps them as `SkillExecutionError` (HTTP 500). Missing skills raise `SkillNotFoundError` (HTTP 404). Both are `AppError` subclasses, so `register_error_handlers()` converts them to typed JSON automatically.

**Currently registered skills:** `guide_qa` (RAG Q&A), `poi_recommend` (AMap POI search), `trip_adjust` (natural-language itinerary editing).

### Error Handling

`register_error_handlers(app)` installs handlers for:
- `AppError` subclasses → JSON `ErrorResponse` with typed `error_code`
- `RequestValidationError` → 422 with field details
- Unhandled `Exception` → 500 (safe message, full traceback logged)

Raise `AppError` subclasses from business logic; avoid `HTTPException` inside service/agent code.

### Rate Limiting

Import `limiter` from `app.api.rate_limit` (not `main.py` — circular import).  
Apply `@limiter.limit("N/minute")` **above** `@router.post(...)`. Handler's first param must be `request: Request`.

Current limits: `/plan/stream` & `/plan` → 5/min · `/adjust` → 10/min · `/guide/ask` & `/guide/skill/poi` → 20/min · `/guide/skill/adjust` → 10/min

When `REDIS_URL` is set, SlowAPI uses Redis as the counter store (distributed, shared across instances). Falls back to `memory://` when unset.

**Known issue**: `SlowAPIMiddleware` is incompatible with `StreamingResponse`. For streaming endpoints, catch `RateLimitExceeded` manually inside `event_generator()`.

### AMap Circuit Breaker

`AmapRestClient` wraps all AMap REST call sites. The breaker trips after 5 consecutive failures (30s recovery window). When open, calls immediately raise `CircuitOpenError` (→ HTTP 503).

- Default: `CircuitBreaker` — in-process, `threading.Lock`-protected
- With `CIRCUIT_BREAKER_REDIS_ENABLED=true` + Redis: `RedisCircuitBreaker` — distributed, shared across instances, Lua atomic state transitions

### Environment Variables

Backend `.env`:
```env
# Required
AMAP_API_KEY=<Web Service Key>
LLM_API_KEY=<your key>
LLM_BASE_URL=https://<openai-compatible>/v1
LLM_MODEL_ID=<model>
JWT_SECRET_KEY=<secret>

# Optional
PORT=8000
CORS_ORIGINS=http://localhost:5173
UNSPLASH_ACCESS_KEY=<key>
TOTAL_TOKEN_BUDGET=16000        # total max_tokens budget per planning request

# Redis (all optional — omit to use local in-memory fallback)
REDIS_URL=redis://localhost:6379/0        # also accepted: MEMORY_REDIS_URL
REDIS_NAMESPACE=trip_agent               # key prefix (default: trip_agent)
REDIS_DISABLE=false                      # emergency kill switch
SESSION_TTL_SECONDS=259200               # also accepted: MEMORY_SESSION_TTL_SECONDS
TRIP_CACHE_TTL_SECONDS=3600
SHARE_TTL_SECONDS=604800
RAG_RERANK_TTL_SECONDS=86400
CIRCUIT_BREAKER_REDIS_ENABLED=false      # opt-in distributed circuit breaker
```

Frontend `.env`:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_JS_KEY=<JS API Key>
VITE_AMAP_SECURITY_CODE=<security code>
```

### Persistent Data (`backend/data/`)

- `trip_planner.db` — SQLite (User, SavedTrip via SQLModel)
- `chroma_guide/` — ChromaDB vector store for guide RAG
- `guide_knowledge.json` — Source knowledge base ingested into ChromaDB
- `user_profiles.json` — User profile store (local fallback when Redis absent)
- `rag_eval_dataset.json` — 15 labeled Q&A pairs for RAG evaluation

### Testing Notes

- `conftest.py` fixtures: `async_client` (no mocks), `client_with_mock_planner` (FakePlanner injected), `sample_trip` (deep-copied dict)
- Tests run without Redis — all Redis paths fall back to local; do not set `REDIS_URL` in test environment
- `validate_skill_flow.py` — skills integration smoke test (not part of pytest suite)
- `evaluate_rag.py` — standalone RAG eval CLI, not run by default pytest
