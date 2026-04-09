"""行程 JSON 解析工具

消除 trip_planner_agent.py 中重复出现两次的 _extract_json_str 逻辑，
提供统一的 parse_trip_response / parse_adjust_response 公共函数。
"""

from __future__ import annotations

import json

from loguru import logger

from ..models.schemas import TripPlan, TripRequest


def extract_json_str(text: str) -> str:
    """从 LLM 响应文本中提取 JSON 字符串

    策略（优先级由高到低）：
      1. ```json ... ``` 代码块
      2. ``` ... ``` 代码块（内容以 { 开头）
      3. 裸 { ... } 最外层大括号
    """
    # 策略 1：```json 块
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()

    # 策略 2：普通 ``` 块
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            candidate = text[start:end].strip()
            if candidate.startswith("{"):
                return candidate

    # 策略 3：裸大括号
    if "{" in text:
        brace_count = 0
        start_idx = text.find("{")
        for i, ch in enumerate(text[start_idx:], start_idx):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx: i + 1]

    raise ValueError("响应中未找到 JSON 数据")


def parse_trip_response(response: str, request: TripRequest) -> TripPlan | None:
    """将 Planner LLM 响应解析为 TripPlan。

    解析失败时返回 None（调用方负责降级处理）。
    """
    raw_preview = response[:300].replace("\n", "\\n") if response else "(empty)"
    logger.debug(f"📄 planner_response 前300字符: {raw_preview}")

    try:
        json_str = extract_json_str(response)
        data = json.loads(json_str)
        trip_plan = TripPlan.model_validate(data)
        logger.success("✅ planner 响应 JSON 解析成功")
        return trip_plan
    except Exception as e:
        logger.warning(f"⚠️ 解析响应失败 ({type(e).__name__}: {e})")
        logger.debug(f"📄 完整 planner_response:\n{response[:2000]}")
        return None


def parse_adjust_response(response: str, original_plan: TripPlan) -> TripPlan:
    """将行程调整 LLM 响应解析为 TripPlan。

    解析失败时返回原始行程（安全降级）。
    """
    try:
        json_str = extract_json_str(response)
        data = json.loads(json_str)
        return TripPlan.model_validate(data)
    except Exception as e:
        logger.warning(f"⚠️ 调整响应解析失败（{e}），返回原始行程")
        return original_plan
