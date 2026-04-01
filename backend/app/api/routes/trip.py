"""旅行规划API路由"""

import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from ...api.rate_limit import limiter
from loguru import logger
from ...models.schemas import (
    TripRequest,
    TripPlan,
    TripPlanResponse,
    TripAdjustRequest,
)
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...services.cache_service import trip_cache
from ...services.pdf_service import generate_trip_pdf

router = APIRouter(prefix="/trip", tags=["旅行规划"])


# ===================== #14 SSE 流式接口 =====================

@limiter.limit("5/minute")
@router.post(
    "/plan/stream",
    summary="流式生成旅行计划（SSE）",
    description="使用 Server-Sent Events 实时推送每个 Agent 步骤的进度，最终返回完整行程数据"
)
async def plan_trip_stream(request: Request, request_body: TripRequest):
    """
    SSE 流式旅行规划接口

    前端使用 fetch + ReadableStream 消费，每个事件格式为：
      data: {"type": "progress", "percent": 50, "message": "..."}\n\n
      data: {"type": "done", "data": {...TripPlan...}}\n\n
      data: {"type": "error", "message": "..."}\n\n
    """
    agent = get_trip_planner_agent()

    async def event_generator():
        try:
            async for event in agent.plan_trip_stream(request_body):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            logger.error(f"SSE 流生成异常: {e}")
            error_payload = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
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


# ===================== 原有 JSON 接口（保持向后兼容，已集成缓存+并行） =====================

@limiter.limit("5/minute")
@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划（JSON）",
    description="一次性返回完整旅行计划（内部走同一套并行+缓存逻辑）"
)
async def plan_trip(request: Request, request_body: TripRequest):
    """生成旅行计划（非流式，等待所有 Agent 完成后一次性返回）"""
    try:
        logger.info(f"📥 旅行规划请求: {request_body.city} {request_body.start_date}~{request_body.end_date}")
        agent = get_trip_planner_agent()

        trip_plan_data = None
        async for event in agent.plan_trip_stream(request_body):
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


# ===================== 功能20：AI 行程调整对话 =====================

@limiter.limit("10/minute")
@router.post(
    "/adjust",
    response_model=TripPlanResponse,
    summary="AI 行程调整（自然语言修改）",
    description="用户用自然语言描述修改要求，AI 返回更新后的行程（无需重新搜索)"
)
async def adjust_trip(request: Request, body: TripAdjustRequest):
    """
    功能20：AI 行程调整对话。
    接收当前 TripPlan + 用户自然语言要求，由 Planner Agent 局部修改并返回新行程。

    调用频次较高时建议在路由层加限流（slowapi 等），防止 LLM 费用超支。
    """
    if not body.user_message.strip():
        raise HTTPException(status_code=400, detail="调整要求不能为空")
    if len(body.user_message) > 500:
        raise HTTPException(status_code=400, detail="调整要求不超过 500 字")

    try:
        logger.info(f"🔧 AI 行程调整请求: {body.user_message[:80]}")
        agent = get_trip_planner_agent()
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


# ===================== 功能22：PDF 行程册导出 =====================

@router.post(
    "/export/pdf",
    summary="导出行程 PDF（后端 ReportLab）",
    description="接收完整 TripPlan，后端使用 ReportLab 生成结构化中文 PDF 并直接下载",
    response_class=Response,
)
async def export_trip_pdf(plan: TripPlan):
    """
    功能22：后端 PDF 行程册。
    对比前端 html2canvas 截图方案，ReportLab 输出矢量文字、完整中文支持、文件体积更小。
    """
    try:
        logger.info(f"📄 PDF 导出请求: {plan.city} {plan.start_date}")
        pdf_bytes = generate_trip_pdf(plan)
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

@router.get(
    "/cache/stats",
    summary="查看缓存统计",
    description="查看当前内存缓存的条目数和 Key 列表"
)
async def get_cache_stats():
    return {"success": True, "data": trip_cache.stats()}


@router.delete(
    "/cache",
    summary="清空缓存",
    description="手动清空所有行程缓存"
)
async def clear_cache():
    trip_cache.clear()
    return {"success": True, "message": "缓存已清空"}


# ===================== 健康检查 =====================

@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        agent = get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
            "agent_name": "MultiAgentTripPlanner",
            "cache_size": trip_cache.size(),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
