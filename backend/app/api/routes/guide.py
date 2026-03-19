"""导游 RAG API 路由（功能27）"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from ...models.schemas import GuideAskRequest, GuideAskResponse, GuideReference
from ...services.rag_service import ask_guide_async

router = APIRouter(prefix="/guide", tags=["导游RAG"])


@router.post(
    "/ask",
    response_model=GuideAskResponse,
    summary="导游问答（RAG）",
    description="基于本地旅游知识库检索 + LLM 生成景点导览回答",
)
async def ask_guide(body: GuideAskRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        logger.info(f"🧭 导游问答请求: {question[:80]}")
        result = await ask_guide_async(
            question=question,
            city=body.city,
            attraction_name=body.attraction_name or "",
            trip_plan=body.trip_plan,
            top_k=body.top_k,
        )

        references = [GuideReference(**item) for item in result.get("references", [])]
        return GuideAskResponse(
            success=True,
            answer=result.get("answer", ""),
            references=references,
            message="导游问答成功",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 导游问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"导游问答失败: {str(e)}")
