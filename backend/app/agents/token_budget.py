"""Token 预算分配器

按子任务复杂度比例从总预算中分配 max_tokens，对应用户提供的
allocateBudgetByComplexity 逻辑，用 Python 实现并适配本项目的三阶段结构。

各阶段说明：
- gather_agent  : 工具调用型 Agent，输出为简短摘要，权重小
- day_plan      : 单日行程 JSON 生成，结构固定，按天线性叠加
- full_plan     : 整体兜底规划，一次生成全程 JSON，权重 = per_day × N
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# ── 相对复杂度权重（对应 Subtask.Complexity）────────────────────────────────

_COMPLEXITY: Dict[str, float] = {
    "gather_agent": 0.03,       # 单个 gather Agent（4 个）
    "day_plan": 0.20,           # 并行逐日规划（每天）
    "full_plan_per_day": 0.28,  # 整体兜底模式（每天，比逐日更高因为结构复杂）
}

_MIN_TOKENS: int = 512          # 任意任务的最低配额，防止截断
DEFAULT_TOTAL: int = 16_000     # 默认总预算（可通过配置覆盖）


# ── 分配结果 ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BudgetPlan:
    """已分配完成的预算计划（不可变）"""
    gather: int          # 每个 gather Agent 的 max_tokens
    day_plan: int        # 每天逐日规划的 max_tokens
    full_plan: int       # 整体兜底规划的 max_tokens（全程）
    total_budget: int    # 传入的总预算
    travel_days: int     # 行程天数

    def __str__(self) -> str:
        return (
            f"BudgetPlan(total={self.total_budget}, days={self.travel_days}, "
            f"gather={self.gather}, day_plan={self.day_plan}, full_plan={self.full_plan})"
        )


# ── 核心分配函数（对应 allocateBudgetByComplexity）───────────────────────────

def allocate(
    total_budget: int,
    travel_days: int,
    n_gather_agents: int = 4,
) -> BudgetPlan:
    """按复杂度比例分配 token 预算。

    总复杂度 = n_gather × gather_weight + days × day_weight + days × full_weight
    每项分配 = total × (item_complexity / total_complexity)

    Args:
        total_budget:    总 token 预算
        travel_days:     行程天数（动态调整 day_plan 和 full_plan 权重）
        n_gather_agents: gather 阶段 Agent 数量（默认 4）

    Returns:
        BudgetPlan（不可变）
    """
    gather_total = n_gather_agents * _COMPLEXITY["gather_agent"]
    day_total    = travel_days * _COMPLEXITY["day_plan"]
    full_total   = travel_days * _COMPLEXITY["full_plan_per_day"]

    total_complexity = gather_total + day_total + full_total

    def _alloc(weight: float) -> int:
        return max(_MIN_TOKENS, int(total_budget * weight / total_complexity))

    return BudgetPlan(
        gather=_alloc(_COMPLEXITY["gather_agent"]),
        day_plan=_alloc(_COMPLEXITY["day_plan"]),
        full_plan=_alloc(full_total),           # full_plan 直接拿全程权重
        total_budget=total_budget,
        travel_days=travel_days,
    )
