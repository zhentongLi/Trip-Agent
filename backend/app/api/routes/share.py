"""行程分享 API 路由（功能21：行程分享）

使用 ShareStore（内存 KV + TTL 7天），重启后失效。
若需持久化可将 ShareStore 替换为 Redis 或数据库后端。
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from ...models.schemas import TripPlan, TripPlanResponse, ShareCreateRequest, ShareCreateResponse
from ...services.share_service import share_store

router = APIRouter(prefix="/trip", tags=["行程分享"])


@router.post(
    "/share",
    response_model=ShareCreateResponse,
    summary="创建行程分享链接（TTL 7天）",
    description="将行程计划存入服务端（内存，7天过期），返回 8 位分享 Token"
)
async def create_share(body: ShareCreateRequest, request: Request):
    """
    创建分享链接。
    - 返回 share_id（8位随机Token）和完整分享 URL
    - 有效期 7 天（ShareStore TTL）
    """
    plan_data = body.plan.model_dump()
    title = body.title or f"{body.plan.city} {body.plan.start_date}行程"
    share_id = share_store.create(plan_data, title=title)

    # 构建绝对 URL（兼容反向代理）
    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/result?share={share_id}"
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    logger.info(f"✅ 行程已分享 share_id={share_id}，城市={body.plan.city}，标题={title}")
    return ShareCreateResponse(
        success=True,
        share_id=share_id,
        share_url=share_url,
        expires_at=expires_at,
        message="分享链接创建成功，7天内有效",
    )


@router.get(
    "/share/{share_id}",
    response_model=TripPlanResponse,
    summary="获取分享的行程",
    description="根据分享ID获取行程计划数据"
)
async def get_shared_trip(share_id: str):
    """
    获取分享行程

    Args:
        share_id: 分享ID

    Returns:
        TripPlanResponse: 行程计划
    """
    item = share_store.get(share_id)
    if item is None:
        logger.warning(f"分享链接不存在或已过期: share_id={share_id}")
        raise HTTPException(
            status_code=404,
            detail=f"分享链接 '{share_id}' 不存在或已过期（7天有效期），请重新分享"
        )

    logger.info(f"📋 获取分享行程 share_id={share_id}，标题={item.get('title', '')}")
    return TripPlanResponse(
        success=True,
        message="获取成功",
        data=TripPlan(**item["plan"])
    )


@router.delete(
    "/share/{share_id}",
    summary="删除分享链接",
    description="主动删除指定分享链接"
)
async def delete_share(share_id: str):
    deleted = share_store.delete(share_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="分享链接不存在或已过期")
    logger.info(f"🗑️ 分享链接已删除: share_id={share_id}")
    return {"success": True, "message": "分享链接已删除"}


@router.get(
    "/share",
    summary="分享统计",
    description="查看当前有效的分享链接数量"
)
async def share_stats():
    return {"success": True, "active_shares": share_store.size()}
