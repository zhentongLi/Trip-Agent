"""旅行规划API路由"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from loguru import logger

from ...api.rate_limit import limiter
from ...agents.planner import MultiAgentTripPlanner
from ...dependencies import get_trip_planner, get_trip_cache, get_current_user_id, get_optional_user_id
from ...models.schemas import TripRequest, TripPlan, TripPlanResponse, TripAdjustRequest
from ...services.cache_service import TTLCache
from ...services.pdf_service import generate_trip_pdf

router = APIRouter(prefix="/trip", tags=["旅行规划"])


# ===================== SSE 流式接口 =====================

@limiter.limit("5/minute")
@router.post(
    "/plan/stream",
    summary="流式生成旅行计划（SSE）",
    description="使用 Server-Sent Events 实时推送每个 Agent 步骤的进度，最终返回完整行程数据",
)
async def plan_trip_stream(
    request: Request,
    request_body: TripRequest,
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    cache: TTLCache = Depends(get_trip_cache),
    user_id: int | None = Depends(get_optional_user_id),
):
    """SSE 流式旅行规划接口"""

    async def event_generator():
        try:
            async for event in agent.plan_trip_stream(request_body, cache=cache):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            logger.error(f"SSE 流生成异常: {e}")
            error_payload = json.dumps(
                {"type": "error", "message": str(e)}, ensure_ascii=False
            )
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===================== JSON 接口（向后兼容） =====================

@limiter.limit("5/minute")
@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划（JSON）",
    description="一次性返回完整旅行计划",
)
async def plan_trip(
    request: Request,
    request_body: TripRequest,
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    cache: TTLCache = Depends(get_trip_cache),
    user_id: int | None = Depends(get_optional_user_id),
):
    """生成旅行计划（非流式）"""
    try:
        logger.info(f"📥 旅行规划请求: {request_body.city} {request_body.start_date}~{request_body.end_date}")

        trip_plan_data = None
        async for event in agent.plan_trip_stream(request_body, cache=cache):
            if event.get("type") == "done":
                trip_plan_data = event["data"]
            elif event.get("type") == "error":
                raise HTTPException(status_code=500, detail=f"规划失败: {event.get('message')}")

        if trip_plan_data is None:
            raise HTTPException(status_code=500, detail="旅行计划生成失败（无数据返回）")

        trip_plan = TripPlan(**trip_plan_data)
        logger.success("✅ 旅行计划生成成功")
        return TripPlanResponse(success=True, message="旅行计划生成成功", data=trip_plan)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


# ===================== AI 行程调整 =====================

@limiter.limit("10/minute")
@router.post(
    "/adjust",
    response_model=TripPlanResponse,
    summary="AI 行程调整（自然语言修改）",
    description="用户用自然语言描述修改要求，AI 返回更新后的行程",
)
async def adjust_trip(
    request: Request,
    body: TripAdjustRequest,
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    user_id: int | None = Depends(get_optional_user_id),
):
    """AI 行程调整对话"""
    if not body.user_message.strip():
        raise HTTPException(status_code=400, detail="调整要求不能为空")
    if len(body.user_message) > 500:
        raise HTTPException(status_code=400, detail="调整要求不超过 500 字")

    try:
        logger.info(f"🔧 AI 行程调整请求: {body.user_message[:80]}")
        adjusted_plan = await agent.adjust_trip(
            trip_plan=body.trip_plan,
            user_message=body.user_message,
            city=body.city or body.trip_plan.city,
        )
        logger.success("✅ AI 行程调整成功")
        return TripPlanResponse(success=True, message="行程已根据您的要求调整", data=adjusted_plan)
    except Exception as e:
        logger.error(f"❌ AI 行程调整失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程调整失败: {str(e)}")


# ===================== PDF 导出 =====================

@router.post(
    "/export/pdf",
    summary="导出行程 PDF",
    response_class=Response,
)
async def export_trip_pdf(plan: TripPlan):
    """后端 ReportLab PDF 导出"""
    try:
        logger.info(f"📄 PDF 导出请求: {plan.city} {plan.start_date}")
        pdf_bytes = await asyncio.to_thread(generate_trip_pdf, plan)
        filename = f"trip_{plan.city}_{plan.start_date}.pdf"
        logger.success(f"✅ PDF 生成成功，大小: {len(pdf_bytes):,} bytes")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"❌ PDF 生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {str(e)}")


# ===================== 缓存管理 =====================

@router.get("/cache/stats", summary="查看缓存统计")
async def get_cache_stats(
    cache: TTLCache = Depends(get_trip_cache),
    _: int = Depends(get_current_user_id),
):
    return {"success": True, "data": cache.stats()}


@router.delete("/cache", summary="清空缓存")
async def clear_cache(
    cache: TTLCache = Depends(get_trip_cache),
    _: int = Depends(get_current_user_id),
):
    cache.clear()
    return {"success": True, "message": "缓存已清空"}


# ===================== 健康检查 =====================

@router.get("/health", summary="健康检查")
async def health_check(
    agent: MultiAgentTripPlanner = Depends(get_trip_planner),
    cache: TTLCache = Depends(get_trip_cache),
):
    return {
        "status": "healthy",
        "service": "trip-planner",
        "agent_name": "MultiAgentTripPlanner",
        "cache_size": cache.size(),
    }
