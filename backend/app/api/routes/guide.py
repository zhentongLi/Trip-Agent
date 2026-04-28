"""导游 RAG / Skill 路由（功能27）

路由结构：
  GET  /api/skills            — Skill 发现接口，列出所有已注册 Skill 的元数据
  POST /api/guide/ask         — 导游问答（GuideQASkill）
  POST /api/guide/skill/poi   — POI 推荐（POIRecommendSkill）
  POST /api/guide/skill/adjust — 行程调整（TripAdjustSkill）
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from ...api.rate_limit import limiter
from ...dependencies import get_skill_router
from ...errors import SkillExecutionError, SkillNotFoundError
from ...models.schemas import (
    GuideAskRequest,
    GuideAskResponse,
    GuideReference,
    POIRecommendRequest,
    POIRecommendResponse,
    POIRecommendPlace,
    SkillInfo,
    SkillListResponse,
    TripAdjustSkillRequest,
    TripAdjustSkillResponse,
    TripPlan,
)
from ...skills.router import SkillRouter

# 导游 / Skill 路由
router = APIRouter(tags=["Skills & 导游RAG"])

# Skill 发现接口（全局路径，不加 /guide 前缀）
skill_discovery_router = APIRouter()


# ─────────────────────────────────────────────────────────
# GET /api/skills  —  Skill 发现
# ─────────────────────────────────────────────────────────

@skill_discovery_router.get(
    "/skills",
    response_model=SkillListResponse,
    summary="列出所有已注册 Skill",
    description="返回当前服务注册的所有 Skill 名称及功能描述，供客户端动态发现可用能力。",
)
async def list_skills(
    skill_router: SkillRouter = Depends(get_skill_router),
):
    skills_data = skill_router.list_skills()
    skills = [SkillInfo(**s) for s in skills_data]
    return SkillListResponse(skills=skills, total=len(skills))


# ─────────────────────────────────────────────────────────
# POST /api/guide/ask  —  导游问答（GuideQASkill）
# ─────────────────────────────────────────────────────────

@limiter.limit("20/minute")
@router.post(
    "/guide/ask",
    response_model=GuideAskResponse,
    summary="导游问答（RAG）",
    description="基于本地旅游知识库检索 + LLM 生成景点导览回答",
)
async def ask_guide(
    request: Request,
    body: GuideAskRequest,
    skill_router: SkillRouter = Depends(get_skill_router),
):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        logger.info(f"🧭 导游问答请求: {question[:80]}")
        result = await skill_router.dispatch(
            "guide_qa",
            {
                "question": question,
                "session_id": body.session_id,
                "debug": body.debug,
                "city": body.city,
                "attraction_name": body.attraction_name or "",
                "trip_plan": body.trip_plan,
                "top_k": body.top_k,
            },
        )

        references = [GuideReference(**item) for item in result.get("references", [])]
        retrieval_meta = result.get("retrieval_meta", {}) or {}
        skill_meta = result.get("skill_meta", {}) or {}
        debug_meta = None
        if body.debug:
            debug_meta = {
                "skill_meta": skill_meta,
                "retrieval_meta": retrieval_meta,
            }

        if retrieval_meta:
            logger.info(
                "🎯 命中摘要 | skill={} | local_kb_hit={} | sources={} | queries={} | rounds={}",
                skill_meta.get("skill_name", "unknown"),
                retrieval_meta.get("has_local_kb_hit", False),
                retrieval_meta.get("source_counts", {}),
                len(retrieval_meta.get("rewritten_queries", []) or []),
                retrieval_meta.get("iterative_rounds", 0),
            )

        return GuideAskResponse(
            success=True,
            answer=result.get("answer", ""),
            references=references,
            debug_meta=debug_meta,
            message="导游问答成功",
        )
    except (SkillNotFoundError, SkillExecutionError) as e:
        logger.error(f"❌ Skill 执行失败: {e}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 导游问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"导游问答失败: {str(e)}")


# ─────────────────────────────────────────────────────────
# POST /api/guide/skill/poi  —  POI 推荐（POIRecommendSkill）
# ─────────────────────────────────────────────────────────

@limiter.limit("20/minute")
@router.post(
    "/guide/skill/poi",
    response_model=POIRecommendResponse,
    summary="POI 地点推荐",
    description="基于高德地图 POI 搜索，推荐景点、餐厅、酒店等地点列表",
)
async def recommend_poi(
    request: Request,
    body: POIRecommendRequest,
    skill_router: SkillRouter = Depends(get_skill_router),
):
    try:
        logger.info(f"📍 POI 推荐请求: city={body.city} | keywords={body.keywords or body.category}")
        result = await skill_router.dispatch(
            "poi_recommend",
            {
                "city": body.city,
                "keywords": body.keywords,
                "category": body.category,
                "limit": body.limit,
            },
        )

        places = [POIRecommendPlace(**p) for p in result.get("places", [])]
        return POIRecommendResponse(
            success=True,
            city=result.get("city", body.city),
            keywords=result.get("keywords", ""),
            total=result.get("total", len(places)),
            places=places,
            message="POI 推荐成功",
        )
    except (SkillNotFoundError, SkillExecutionError) as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ POI 推荐失败: {e}")
        raise HTTPException(status_code=500, detail=f"POI 推荐失败: {str(e)}")


# ─────────────────────────────────────────────────────────
# POST /api/guide/skill/adjust  —  行程调整（TripAdjustSkill）
# ─────────────────────────────────────────────────────────

@limiter.limit("10/minute")
@router.post(
    "/guide/skill/adjust",
    response_model=TripAdjustSkillResponse,
    summary="AI 行程调整（Skill 入口）",
    description="用自然语言描述调整要求，AI 返回更新后的行程（与 /trip/adjust 功能相同，通过 Skill 体系调用）",
)
async def adjust_trip_skill(
    request: Request,
    body: TripAdjustSkillRequest,
    skill_router: SkillRouter = Depends(get_skill_router),
):
    try:
        logger.info(f"✏️ 行程调整 Skill 请求: {body.user_message[:60]}")
        result = await skill_router.dispatch(
            "trip_adjust",
            {
                "user_message": body.user_message,
                "trip_plan": body.trip_plan.model_dump(),
                "city": body.city,
            },
        )

        adjusted_data = result.get("adjusted_plan")
        adjusted_plan = TripPlan(**adjusted_data) if adjusted_data else None

        return TripAdjustSkillResponse(
            success=True,
            adjusted_plan=adjusted_plan,
            message="行程已根据您的要求调整",
        )
    except (SkillNotFoundError, SkillExecutionError) as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 行程调整 Skill 失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程调整失败: {str(e)}")
