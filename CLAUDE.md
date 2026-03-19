# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (FastAPI + LangGraph)

```bash
cd backend

# Run tests (31 test cases)
conda run -n trip-agent python -m pytest tests/ -q

# Start development server
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

# Install dependencies
pip install -r requirements.txt
```

### Frontend (Vue 3 + TypeScript + Vite)

```bash
cd frontend

# Development server
npm run dev

# Production build
npm run build

# Preview build
npm run preview
```

### One-Command Start

From project root:
```bash
bash start.sh
```
Starts backend on port 8000, frontend on port 5173.

### Docker

```bash
docker-compose up --build
```

## High-Level Architecture

### Project Overview

AI-powered travel planning platform with:
- 5-Agent parallel orchestration (Attraction, Weather, Hotel, Food, Planner)
- SSE streaming progress (Start → Search → Plan → Postprocess → Complete)
- Multi-city tour support with automatic day allocation
- Guide RAG Q&A with local knowledge base
- JWT authentication + SQLite cloud storage
- Features: PDF export, AI trip adjustment, shareable links (7-day TTL)

### Backend Architecture (`backend/app/`)

```
app/
├── agents/trip_planner_agent.py   # LangGraph StateGraph: gather → plan → postprocess
├── api/
│   ├── main.py                    # FastAPI app, CORS, router registration
│   └── routes/
│       ├── trip.py                # /api/trip/* (plan/stream, adjust, export/pdf, share, cache)
│       ├── guide.py               # /api/guide/ask (RAG Q&A)
│       ├── auth.py                # /api/auth/* (register, login, me)
│       ├── user.py                # /api/user/* (CRUD cloud trips)
│       ├── share.py               # Share link management (7-day TTL cache)
│       ├── map.py                 # /api/map/* (POI, weather, route)
│       └── poi.py                 # Low-level POI search
├── services/
│   ├── amap_service.py            # AMap REST API wrapper
│   ├── llm_service.py             # LLM client (OpenAI-compatible)
│   ├── rag_service.py             # Guide RAG retrieval
│   ├── pdf_service.py             # ReportLab PDF generation
│   ├── auth_service.py            # JWT token handling
│   ├── share_service.py           # Share link cache (Redis-like TTL)
│   └── cache_service.py           # Trip cache (in-memory)
├── models/
│   ├── schemas.py                 # Pydantic v2 models (TripRequest, TripPlan, etc.)
│   └── db_models.py               # SQLModel tables (User, SavedTrip)
└── config.py                      # pydantic-settings, env loading
```

### LangGraph Agent Flow

```
START → gather → plan → postprocess → END

gather:     Parallel 4-Agent calls (Attraction, Weather, Hotel, Food)
            - Uses StructuredTool for AMap REST API (search_places, get_weather)
            - Concurrent with asyncio.gather()

plan:       Planner LLM integrates data → JSON TripPlan
            - Retry logic with exponential backoff
            - _is_retryable_llm_error() handles 502/503/timeouts

postprocess:
            - _fix_coordinates(): Geocode attraction addresses
            - _add_weather_warnings(): Extreme weather alerts
            - _enrich_opening_hours(): Real-time POI hours
```

### Frontend Architecture (`frontend/src/`)

```
src/
├── App.vue                      # Router view, global providers
├── views/
│   ├── Home.vue                 # Trip planning form, SSE progress display
│   └── Result.vue               # Map (AMap JS API), budget, weather, itinerary
├── services/
│   ├── api.ts                   # Axios + fetch SSE stream, localStorage history
│   └── auth.ts                  # Reactive auth state (no Pinia)
└── types/index.ts               # TypeScript interfaces
```

### Key Data Flow

```
Home Form → POST /api/trip/plan/stream (SSE)
          → MultiAgentTripPlanner.plan_trip_stream()
             1. Cache check (cache_service.trip_cache)
             2. LangGraph.astream(initial_state)
             3. gather node: 4 parallel agents → attraction/weather/hotel/food
             4. plan node: LLM generates JSON TripPlan
             5. postprocess: coordinate fix, weather warnings, opening hours
             6. Write cache, stream SSE events
          → Result view renders map, budget, weather, daily itinerary
```

### API Endpoints Summary

| Prefix | Route | Description |
|--------|-------|-------------|
| `/api/trip` | `POST /plan/stream` | SSE streaming generation |
| | `POST /plan` | JSON one-shot |
| | `POST /adjust` | AI natural language adjustment |
| | `POST /export/pdf` | ReportLab PDF export |
| | `GET /cache/stats`, `DELETE /cache` | Cache management |
| | `POST /share`, `GET /share/{id}` | Share links (7-day TTL) |
| `/api/guide` | `POST /ask` | RAG Q&A with trip context |
| `/api/auth` | `POST /register`, `/login`, `GET /me` | JWT auth |
| `/api/user` | `GET /trips`, `POST /trips`, `DELETE /trips/{id}` | Cloud trip CRUD |
| `/api/map` | `GET /poi`, `/weather`, `POST /route` | AMap utilities |

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
```

Frontend `.env`:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_JS_KEY=<JS API Key>
VITE_AMAP_SECURITY_CODE=<security code>
```

### Testing

Tests in `backend/tests/`:
- `test_routes.py`: API route tests
- `test_schemas.py`: Pydantic model validation
- `test_share_service.py`: Share service TTL logic

Fixtures in `conftest.py` provide `async_client` and `sample_trip`.
