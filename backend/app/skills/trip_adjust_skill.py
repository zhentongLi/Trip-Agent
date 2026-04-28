"""行程调整 Skill（功能：自然语言修改已有行程）。"""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from .base import RuntimeSkill


class TripAdjustSkill(RuntimeSkill):
    """封装 AI 行程调整能力。

    将原本散落在 trip.py 路由中的 adjust_trip 调用抽象为 Skill，
    使前端可通过统一的 /guide/ask 入口（skill_name="trip_adjust"）触发，
    无需维护额外的 API 端点。

    构造参数:
        planner: MultiAgentTripPlanner 实例（提供 adjust_trip 方法）。
    """

    name = "trip_adjust"
    description = "用自然语言描述修改要求，AI 自动调整已有旅行行程"

    def __init__(self, planner: Any) -> None:
        """
        Args:
            planner: MultiAgentTripPlanner 实例。
        """
        self._planner = planner

    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行行程调整。

        payload 期望字段：
            user_message (str):  用户的自然语言调整要求（必填）。
            trip_plan    (dict): 当前行程 JSON（必填）。
            city         (str):  主城市，用于坐标修正（可选）。
        """
        user_message = str(payload.get("user_message", "")).strip()
        if not user_message:
            raise ValueError("user_message 不能为空")
        if len(user_message) > 500:
            raise ValueError("user_message 不超过 500 字")

        trip_plan_data = payload.get("trip_plan")
        if not trip_plan_data:
            raise ValueError("trip_plan 不能为空")

        city = str(payload.get("city", ""))

        logger.info(
            "🧩 Skill命中: {} | city={} | message={}",
            self.name,
            city or "-",
            user_message[:60],
        )

        # 将 dict 转为 TripPlan Pydantic 模型（planner.adjust_trip 接受该类型）
        from ..models.schemas import TripPlan
        trip_plan = TripPlan(**trip_plan_data) if isinstance(trip_plan_data, dict) else trip_plan_data

        adjusted_plan = await self._planner.adjust_trip(
            trip_plan=trip_plan,
            user_message=user_message,
            city=city or trip_plan.city,
        )

        return {
            "adjusted_plan": adjusted_plan.model_dump(),
            "skill_meta": {
                "skill_name": self.name,
                "skill_description": self.description,
                "user_message": user_message,
            },
        }
