"""LangGraph 状态定义"""

from __future__ import annotations

from typing import List, Optional

from typing_extensions import TypedDict

from ..models.schemas import TripPlan, TripRequest


class PlannerState(TypedDict):
    """LangGraph 各节点间共享的状态字典"""

    request: TripRequest
    cities: List[str]
    primary_city: str
    attraction_response: str
    weather_response: str
    hotel_response: str
    food_response: str
    trip_plan: Optional[TripPlan]
    error: Optional[str]
    user_profile_hint: Optional[str]  # 个性化偏好摘要，由 MemoryService 注入，供 Planner prompt 使用
