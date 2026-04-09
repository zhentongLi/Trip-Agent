# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (FastAPI + LangGraph)

```bash
cd backend

# Run all tests (31 test cases)
conda run -n trip-agent python -m pytest tests/ -q

# Run a single test file
conda run -n trip-agent python -m pytest tests/test_routes.py -q

# Run a single test by name
conda run -n trip-agent python -m pytest tests/test_routes.py::TestTripAdjust::test_adjust_rejects_empty_message -q

# Start development server
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

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
│   ├── rate_limit.py    # limiter singleton — always import from here (avoid circular)
│   └── routes/          # All route handlers use Depends() — no direct singleton calls
│       ├── trip.py      # /api/trip/* — injects MultiAgentTripPlanner + TTLCache
│       ├── guide.py     # /api/guide/ask — injects SkillRouter
│       ├── share.py     # Share link management
│       ├── auth.py      # JWT auth
│       ├── user.py      # Cloud trip CRUD
│       └── map.py       # AMap POI/weather/route utilities
├── agents/              # LangGraph multi-agent system (split from monolith in Phase 4)
│   ├── planner.py       # MultiAgentTripPlanner — public API: plan_trip_stream, plan_trip, adjust_trip
│   ├── nodes.py         # NodeFactory — gather / plan / postprocess LangGraph nodes
│   ├── parsers.py       # extract_json_str, parse_trip_response, parse_adjust_response
│   ├── prompts.py       # All 5 agent system prompts (ATTRACTION, WEATHER, HOTEL, FOOD, PLANNER)
│   ├── state.py         # PlannerState TypedDict
│   ├── tools.py         # make_amap_tools(client) → (search_places_tool, get_weather_tool)
│   └── trip_planner_agent.py  # ← compatibility shim only; do not add logic here
├── dependencies.py      # ALL FastAPI Depends() factories (get_llm, get_amap_client,
│                        #   get_trip_planner, get_trip_cache, get_share_store, get_skill_router)
├── errors/
│   ├── types.py         # Exception hierarchy: AppError → ExternalServiceError → CircuitOpenError, etc.
│   ├── schemas.py       # ErrorResponse Pydantic model
│   └── handlers.py      # register_error_handlers(app) — called once in main.py
├── services/
│   ├── amap_rest_client.py  # AmapRestClient: search_places, get_weather, geocode, get_opening_hours
│   │                        #   All calls go through CircuitBreaker (5 failures → 30s open)
│   ├── circuit_breaker.py   # CircuitBreaker: CLOSED → OPEN → HALF_OPEN state machine
│   ├── cache_service.py     # TTLCache (in-memory, GIL-safe) + make_trip_cache_key()
│   ├── llm_service.py       # get_llm() factory — kept for legacy; prefer dependencies.py
│   ├── rag_service.py       # ChromaDB + BM25 hybrid retrieval, optional CrossEncoder reranking
│   ├── share_service.py     # ShareStore — in-memory 7-day TTL
│   ├── memory_service.py    # Two-layer memory: session (Redis/local) + user profile
│   └── pdf_service.py       # ReportLab PDF generation
├── skills/
│   ├── base.py          # RuntimeSkill ABC
│   ├── registry.py      # SkillRegistry
│   ├── router.py        # SkillRouter.dispatch(name, payload)
│   └── guide_qa_skill.py
├── models/
│   ├── schemas.py       # Pydantic v2: TripRequest, TripPlan, DayPlan, Attraction, Meal, …
│   └── db_models.py     # SQLModel: User, SavedTrip (SQLite)
└── config.py            # pydantic-settings (Settings), get_settings(), validate_config()
```

### LangGraph Agent Flow

```
START → gather → plan → postprocess → END

gather:      NodeFactory.gather() — asyncio.gather() 4+ agents in parallel
             Attraction × N cities, Weather × N cities, Hotel, Food

plan:        NodeFactory.plan() — Planner LLM → JSON → parse_trip_response()
             Retries up to 3× on 502/503/timeout via _invoke_with_retry()

postprocess: NodeFactory.postprocess() — synchronous
             _fix_coordinates()     → AmapRestClient.geocode()
             _add_weather_warnings() → regex on weather strings
             _enrich_opening_hours() → AmapRestClient.get_opening_hours()
```

`plan_trip_stream()` accepts an optional `cache` parameter (TTLCache). Pass it from the route via `Depends(get_trip_cache)`.

### Dependency Injection Pattern

All services are provided through `app/dependencies.py`. Routes **must not** call `get_xxx()` functions directly:

```python
# CORRECT — route handler
async def my_route(
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    cache: TTLCache = Depends(get_trip_cache),
): ...

# WRONG — do not do this in routes
agent = get_trip_planner_agent()   # deprecated shim, raises RuntimeError
```

All factories in `dependencies.py` use `@lru_cache()` for process-level singletons.

### Mocking Services in Tests

Use `app.dependency_overrides` — never monkeypatch route modules directly:

```python
from app.api.main import app
from app.dependencies import get_trip_planner
from app.services.cache_service import TTLCache

app.dependency_overrides[get_trip_planner] = lambda: FakePlanner()
app.dependency_overrides[get_trip_cache]   = lambda: TTLCache(ttl_seconds=60)
# ... run test ...
app.dependency_overrides.pop(get_trip_planner, None)
app.dependency_overrides.pop(get_trip_cache, None)
```

The `client_with_mock_planner` fixture in `conftest.py` handles this setup/teardown automatically.

### Error Handling

`register_error_handlers(app)` in `main.py` installs handlers for:
- `AppError` subclasses → JSON `ErrorResponse` with typed `error_code`
- `RequestValidationError` → 422 with field details
- Unhandled `Exception` → 500 (safe message, full traceback logged)

Raise `AppError` subclasses from business logic; avoid `HTTPException` inside service/agent code.

### Rate Limiting

Import `limiter` from `app.api.rate_limit` (not `main.py` — circular import).  
Apply `@limiter.limit("N/minute")` **above** `@router.post(...)`. Handler's first param must be `request: Request`.

Current limits: `/plan/stream` & `/plan` → 5/min · `/adjust` → 10/min · `/guide/ask` → 20/min

**Known issue**: `SlowAPIMiddleware` is incompatible with `StreamingResponse`. For streaming endpoints, rate limiting must be handled manually inside `event_generator()` (catch `RateLimitExceeded`).

### AMap Circuit Breaker

`AmapRestClient` wraps all 5 AMap REST call sites. The `CircuitBreaker` trips after 5 consecutive failures (30s recovery). When open, calls immediately raise `CircuitOpenError` (HTTP 503). The singleton breaker is created in `dependencies.get_amap_client()`.

### Environment Variables

Backend `.env`:
```env
AMAP_API_KEY=<Web Service Key>
LLM_API_KEY=<your key>
LLM_BASE_URL=https://<openai-compatible>/v1
LLM_MODEL_ID=<model>
PORT=8000
CORS_ORIGINS=http://localhost:5173
JWT_SECRET_KEY=<secret>
# Optional
UNSPLASH_ACCESS_KEY=<key>
MEMORY_REDIS_URL=redis://...
MEMORY_REDIS_NAMESPACE=trip_agent:memory
MEMORY_SESSION_TTL_SECONDS=259200
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
- `user_profiles.json` — User profile store
- `rag_eval_dataset.json` — 15 labeled Q&A pairs for RAG evaluation

### Testing Notes

- `conftest.py` fixtures: `async_client` (no mocks), `client_with_mock_planner` (FakePlanner injected), `sample_trip` (deep-copied dict)
- Tests do **not** hit real LLM or AMap — any test requiring those must use `client_with_mock_planner` or equivalent overrides
- `validate_skill_flow.py` — skills integration smoke test (not part of pytest suite)
- `evaluate_rag.py` — standalone RAG eval CLI, not run by default pytest
