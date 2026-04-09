"""导游 RAG API 路由（功能27）"""

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from ...api.rate_limit import limiter
from ...dependencies import get_skill_router
from ...models.schemas import GuideAskRequest, GuideAskResponse, GuideReference
from ...skills.router import SkillRouter

router = APIRouter(prefix="/guide", tags=["导游RAG"])


@limiter.limit("20/minute")
@router.post(
    "/ask",
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 导游问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"导游问答失败: {str(e)}")
