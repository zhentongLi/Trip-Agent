"""
功能23：用户行程云端保存路由
GET    /api/user/trips         — 获取当前用户的所有行程列表
POST   /api/user/trips         — 保存当前行程到云端
GET    /api/user/trips/{id}    — 获取行程详情（含完整 plan_json）
DELETE /api/user/trips/{id}    — 删除行程
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ...dependencies import get_current_user_id
from ...models.db_models import (
    SavedTrip,
    SavedTripOut,
    SavedTripDetail,
    get_session,
)
from ...models.schemas import TripPlan

router = APIRouter(prefix="/user", tags=["用户行程"])


# ─────────────────────────────────────────────────────────────────────────

class SaveTripRequest(TripPlan):
    """保存行程请求（继承 TripPlan，附加可选标题）"""
    title: str = ""


@router.get("/trips", response_model=list[SavedTripOut], summary="获取我的行程列表")
def list_trips(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    trips = session.exec(
        select(SavedTrip).where(SavedTrip.user_id == user_id).order_by(SavedTrip.created_at.desc())
    ).all()
    return [SavedTripOut(id=t.id, city=t.city, title=t.title, created_at=t.created_at) for t in trips]


@router.post("/trips", response_model=SavedTripOut, summary="保存行程到云端")
def save_trip(
    body: SaveTripRequest,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    title = body.title or f"{body.city} {body.start_date} 行程"
    plan_data = body.model_dump()
    plan_data.pop("title", None)

    trip = SavedTrip(
        user_id=user_id,
        city=body.city,
        title=title,
        plan_json=json.dumps(plan_data, ensure_ascii=False),
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return SavedTripOut(id=trip.id, city=trip.city, title=trip.title, created_at=trip.created_at)


@router.get("/trips/{trip_id}", response_model=SavedTripDetail, summary="获取行程详情")
def get_trip(
    trip_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    trip = session.get(SavedTrip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    if trip.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问此行程")
    return SavedTripDetail(
        id=trip.id,
        city=trip.city,
        title=trip.title,
        plan_json=trip.plan_json,
        created_at=trip.created_at,
    )


@router.delete("/trips/{trip_id}", summary="删除行程")
def delete_trip(
    trip_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
):
    trip = session.get(SavedTrip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    if trip.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此行程")
    session.delete(trip)
    session.commit()
    return {"success": True, "message": "行程已删除"}
