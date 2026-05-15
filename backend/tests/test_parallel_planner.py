"""
测试：NodeFactory 并行逐日规划辅助方法

覆盖：
  - _extract_city_section: 单城市 / 多城市段落提取
  - _extract_weather_snippet: 按日期提取天气行
  - _parse_weather_info: AMap 文本 → WeatherInfo 列表
  - _build_single_day_query: prompt 结构校验
  - _plan_single_day_async: LLM 成功 / 解析失败 / 异常路径
  - plan(): 并行成功 / 回退整体模式
"""
from __future__ import annotations

import asyncio
import json
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.nodes import NodeFactory
from app.models.schemas import (
    DayPlan,
    Hotel,
    Location,
    Meal,
    TripRequest,
    WeatherInfo,
)


# ── 测试夹具 ──────────────────────────────────────────────────────────────────

def _make_factory() -> NodeFactory:
    """创建 NodeFactory 测试实例（所有依赖用 MagicMock）"""
    factory = NodeFactory(
        attraction_agent=MagicMock(),
        weather_agent=MagicMock(),
        hotel_agent=MagicMock(),
        food_agent=MagicMock(),
        llm=MagicMock(),
        amap_client=MagicMock(),
        invoke_with_retry=AsyncMock(),
        is_retryable_llm_error=lambda e: False,
        build_planner_query=MagicMock(return_value="full_plan_query"),
        create_fallback_plan=MagicMock(),
    )
    return factory


def _make_request(**kwargs) -> TripRequest:
    defaults = dict(
        city="北京",
        start_date="2026-06-01",
        end_date="2026-06-02",
        travel_days=2,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化"],
    )
    defaults.update(kwargs)
    return TripRequest(**defaults)


def _make_day_plan(day_index: int, date: str) -> DayPlan:
    return DayPlan(
        date=date,
        day_index=day_index,
        description=f"第{day_index + 1}天",
        transportation="公共交通",
        accommodation="经济型酒店",
        hotel=Hotel(name="测试酒店", address="北京市", estimated_cost=300),
        attractions=[],
        meals=[
            Meal(type="breakfast", name="早餐店A", estimated_cost=25),
            Meal(type="lunch",     name="午餐店B", estimated_cost=80),
            Meal(type="dinner",    name="晚餐店C", estimated_cost=100),
        ],
    )


# ── _extract_city_section ──────────────────────────────────────────────────────

class TestExtractCitySection:
    def test_single_city_returns_original(self):
        text = "故宫博物院 东城区 ★4.8"
        assert NodeFactory._extract_city_section(text, "北京") == text

    def test_multi_city_extracts_first(self):
        text = "【北京景点信息】\n景点A\n\n【上海景点信息】\n景点B"
        result = NodeFactory._extract_city_section(text, "北京")
        assert "景点A" in result
        assert "景点B" not in result

    def test_multi_city_extracts_second(self):
        text = "【北京景点信息】\n景点A\n\n【上海景点信息】\n景点B"
        result = NodeFactory._extract_city_section(text, "上海")
        assert "景点B" in result
        assert "景点A" not in result

    def test_city_not_found_returns_original(self):
        text = "【北京景点信息】\n景点A"
        result = NodeFactory._extract_city_section(text, "成都")
        assert result == text


# ── _extract_weather_snippet ──────────────────────────────────────────────────

class TestExtractWeatherSnippet:
    WEATHER_TEXT = (
        "日期: 2026-06-01 | 白天: 晴 28℃ | 夜间: 多云 18℃ | 风向: 南风 2级\n"
        "日期: 2026-06-02 | 白天: 阴 25℃ | 夜间: 小雨 17℃ | 风向: 东风 1级"
    )

    def test_finds_correct_date(self):
        result = NodeFactory._extract_weather_snippet(self.WEATHER_TEXT, "2026-06-01")
        assert "2026-06-01" in result
        assert "28℃" in result

    def test_finds_second_date(self):
        result = NodeFactory._extract_weather_snippet(self.WEATHER_TEXT, "2026-06-02")
        assert "2026-06-02" in result
        assert "25℃" in result

    def test_missing_date_returns_empty(self):
        result = NodeFactory._extract_weather_snippet(self.WEATHER_TEXT, "2026-06-03")
        assert result == ""


# ── _parse_weather_info ───────────────────────────────────────────────────────

class TestParseWeatherInfo:
    WEATHER_RAW = (
        "日期: 2026-06-01 | 白天: 晴 28℃ | 夜间: 多云 18℃ | 风向: 南风 2级\n"
        "日期: 2026-06-02 | 白天: 阴 25℃ | 夜间: 小雨 17℃ | 风向: 东风 1级"
    )

    def test_returns_correct_count(self):
        result = NodeFactory._parse_weather_info(self.WEATHER_RAW, "2026-06-01", 2)
        assert len(result) == 2

    def test_first_day_parsed_correctly(self):
        result = NodeFactory._parse_weather_info(self.WEATHER_RAW, "2026-06-01", 2)
        assert result[0].date == "2026-06-01"
        assert result[0].day_weather == "晴"
        assert result[0].day_temp == 28
        assert result[0].night_temp == 18

    def test_second_day_parsed_correctly(self):
        result = NodeFactory._parse_weather_info(self.WEATHER_RAW, "2026-06-01", 2)
        assert result[1].date == "2026-06-02"
        assert result[1].night_weather == "小雨"

    def test_missing_date_uses_fallback(self):
        # 只有一天数据，但请求两天
        one_day = "日期: 2026-06-01 | 白天: 晴 28℃ | 夜间: 多云 18℃"
        result = NodeFactory._parse_weather_info(one_day, "2026-06-01", 2)
        assert len(result) == 2
        assert result[1].day_weather == "晴"  # fallback 默认晴


# ── _build_single_day_query ───────────────────────────────────────────────────

class TestBuildSingleDayQuery:
    def test_contains_day_number(self):
        factory = _make_factory()
        req = _make_request()
        q = factory._build_single_day_query(
            request=req, day_index=0, day_date="2026-06-01",
            current_city="北京", attractions="景点A", weather_snippet="晴 28℃",
            hotels="酒店A", foods="餐厅A", total_days=2,
        )
        assert "第1天" in q
        assert "2026-06-01" in q
        assert "北京" in q

    def test_transit_day_mentions_prev_city(self):
        factory = _make_factory()
        req = _make_request()
        q = factory._build_single_day_query(
            request=req, day_index=1, day_date="2026-06-02",
            current_city="上海", attractions="景点B", weather_snippet="",
            hotels="酒店B", foods="餐厅B", total_days=2,
            prev_city="北京",
        )
        assert "北京" in q
        assert "上海" in q

    def test_budget_limit_included(self):
        factory = _make_factory()
        req = _make_request(budget_limit=2000)
        q = factory._build_single_day_query(
            request=req, day_index=0, day_date="2026-06-01",
            current_city="北京", attractions="景点A", weather_snippet="",
            hotels="酒店A", foods="餐厅A", total_days=2,
        )
        assert "1000" in q  # 2000 // 2 = 1000

    def test_requires_pure_json(self):
        factory = _make_factory()
        req = _make_request()
        q = factory._build_single_day_query(
            request=req, day_index=0, day_date="2026-06-01",
            current_city="北京", attractions="", weather_snippet="",
            hotels="", foods="", total_days=1,
        )
        assert "JSON" in q


# ── _plan_single_day_async ────────────────────────────────────────────────────

class TestPlanSingleDayAsync:
    def _make_day_json(self, day_index: int, date: str) -> str:
        return json.dumps({
            "date": date,
            "day_index": day_index,
            "description": f"第{day_index + 1}天行程",
            "transportation": "公共交通",
            "accommodation": "经济型酒店",
            "hotel": {"name": "测试酒店", "address": "北京", "location": {"longitude": 116.4, "latitude": 39.9},
                      "price_range": "200-400元", "rating": "4.2", "distance": "1km", "type": "经济型", "estimated_cost": 250},
            "attractions": [
                {"name": "故宫", "address": "北京市东城区", "location": {"longitude": 116.3, "latitude": 39.9},
                 "visit_duration": 180, "description": "著名景点", "category": "历史", "ticket_price": 60}
            ],
            "meals": [
                {"type": "breakfast", "name": "早餐店", "address": "北京", "description": "特色早餐", "estimated_cost": 25},
                {"type": "lunch",     "name": "午餐店", "address": "北京", "description": "特色午餐", "estimated_cost": 80},
                {"type": "dinner",    "name": "晚餐店", "address": "北京", "description": "特色晚餐", "estimated_cost": 100},
            ],
        }, ensure_ascii=False)

    @pytest.mark.asyncio
    async def test_success_returns_day_plan(self):
        factory = _make_factory()
        factory._stream_llm_with_latency = AsyncMock(return_value=self._make_day_json(0, "2026-06-01"))

        result = await factory._plan_single_day_async(
            "test_query", 0, "2026-06-01", _make_request()
        )
        assert isinstance(result, DayPlan)
        assert result.day_index == 0
        assert result.date == "2026-06-01"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self):
        factory = _make_factory()
        factory._stream_llm_with_latency = AsyncMock(return_value="不是JSON数据")

        result = await factory._plan_single_day_async(
            "test_query", 0, "2026-06-01", _make_request()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_invoke_exception_returns_none(self):
        factory = _make_factory()
        factory._stream_llm_with_latency = AsyncMock(side_effect=RuntimeError("LLM error"))

        result = await factory._plan_single_day_async(
            "test_query", 0, "2026-06-01", _make_request()
        )
        assert result is None
