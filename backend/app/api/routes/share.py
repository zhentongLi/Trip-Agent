"""行程分享 API 路由（功能21：行程分享）

ShareStore Redis 可用时持久化，支持跨实例、重启后仍有效；
Redis 不可用时降级为内存 KV（7天 TTL）。

鉴权策略：
  POST  /share   — 可选鉴权（匿名可分享，登录时记录 creator_id）
  GET   /share/* — 匿名公开（不暴露 creator_id）
  DELETE /share/* — 强制鉴权 + 所有权校验
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from ...dependencies import get_share_store, get_current_user_id, get_optional_user_id
from ...errors.types import AuthorizationError, NotFoundError
from ...models.schemas import TripPlan, TripPlanResponse, ShareCreateRequest, ShareCreateResponse
from ...services.share_service import ShareStore

router = APIRouter(prefix="/trip", tags=["行程分享"])


@router.post(
    "/share",
    response_model=ShareCreateResponse,
    summary="创建行程分享链接（TTL 7天）",
    description="将行程计划存入服务端（Redis/内存，7天过期），返回 8 位分享 Token"
)
async def create_share(
    body: ShareCreateRequest,
    request: Request,
    store: ShareStore = Depends(get_share_store),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    plan_data = body.plan.model_dump()
    title = body.title or f"{body.plan.city} {body.plan.start_date}行程"
    share_id = await store.acreate(plan_data, title=title, creator_id=user_id)

    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/result?share={share_id}"
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    logger.info(f"✅ 行程已分享 share_id={share_id}，城市={body.plan.city}，creator={user_id}")
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
    description="根据分享ID获取行程计划数据（公开接口，不暴露创建者信息）"
)
async def get_shared_trip(
    share_id: str,
    store: ShareStore = Depends(get_share_store),
):
    item = await store.aget(share_id)
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
    description="删除自己创建的分享链接（需登录，且只能删除自己的分享）"
)
async def delete_share(
    share_id: str,
    store: ShareStore = Depends(get_share_store),
    user_id: int = Depends(get_current_user_id),
):
    if not await store.acheck_owner(share_id, user_id):
        # 区分「不存在」和「无权限」：先检查是否存在
        item = await store.aget(share_id)
        if item is None:
            raise NotFoundError("分享链接不存在或已过期")
        raise AuthorizationError("无权删除此分享链接")

    deleted = await store.adelete(share_id)
    if not deleted:
        raise NotFoundError("分享链接不存在或已过期")

    logger.info(f"🗑️ 分享链接已删除: share_id={share_id} by user_id={user_id}")
    return {"success": True, "message": "分享链接已删除"}


@router.get(
    "/share",
    summary="分享统计",
    description="查看当前有效的分享链接数量（本地内存，不含 Redis）"
)
async def share_stats(store: ShareStore = Depends(get_share_store)):
    return {"success": True, "active_shares": store.size()}
