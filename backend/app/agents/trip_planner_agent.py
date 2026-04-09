"""向后兼容垫片 — 请从 agents.planner 导入

此文件保留是为了避免外部代码直接 import trip_planner_agent 时报错。
新代码请使用：
    from app.agents.planner import MultiAgentTripPlanner
    from app.dependencies import get_trip_planner
"""

from .planner import MultiAgentTripPlanner  # noqa: F401

# get_trip_planner_agent 已迁移到 app.dependencies，此处保留仅供过渡期使用
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """已废弃：请通过 FastAPI Depends(get_trip_planner) 获取实例。"""
    raise RuntimeError(
        "get_trip_planner_agent() 已废弃。"
        "请在路由函数参数中使用 Depends(get_trip_planner)。"
    )
