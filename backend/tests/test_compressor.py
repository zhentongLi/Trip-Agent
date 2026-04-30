"""
测试：Planner 上下文压缩器（Feature B）

测试矩阵：
  - POI 标准行 → 正确压缩（含名称、区域地址、评分）
  - POI 缺少类型字段 → 不崩溃
  - POI 无法解析行 → 原样返回
  - POI 多行文本 → 逐行压缩
  - 天气标准行 → MM-DD W/W T/T℃ 风向格式
  - 天气缺少风向 → 正常压缩
  - 天气无法解析行 → 原样返回
  - compress_agent_responses 四路输出都被压缩
  - 压缩器内部错误时安全回退
  - 压缩后字符数 < 原始
"""
import pytest

from app.agents.compressor import (
    compress_poi_text,
    compress_weather_text,
    compress_agent_responses,
)

# ── 测试数据 ──────────────────────────────────────────────────────────────────

POI_STANDARD = (
    "名称: 故宫博物院 | 地址: 北京市东城区景山前街4号 | 坐标: 116.3972,39.9179 | 评分: 4.8 | 类型: 历史建筑"
)
POI_NO_TYPE = (
    "名称: 颐和园 | 地址: 北京市海淀区新建宫门路19号 | 坐标: 116.2755,39.9991 | 评分: 4.7"
)
POI_UNPARSEABLE = "这是一行无结构的随机文字，无法解析"

WEATHER_STANDARD = (
    "日期: 2025-08-01 | 白天: 晴 32℃ | 夜间: 晴 22℃ | 风向: 南风 2级"
)
WEATHER_NO_WIND = (
    "日期: 2025-08-02 | 白天: 多云 28℃ | 夜间: 阴 20℃"
)
WEATHER_UNPARSEABLE = "天气数据暂时不可用"


# ── POI 压缩测试 ──────────────────────────────────────────────────────────────

class TestCompressPoi:
    def test_standard_line_contains_name(self):
        result = compress_poi_text(POI_STANDARD)
        assert "故宫博物院" in result

    def test_standard_line_contains_score(self):
        result = compress_poi_text(POI_STANDARD)
        assert "★4.8" in result

    def test_standard_line_contains_address(self):
        result = compress_poi_text(POI_STANDARD)
        # 完整地址被缩短为区级以下，不含"北京市"
        assert "北京市" not in result
        assert "景山前街" in result

    def test_standard_line_contains_type(self):
        result = compress_poi_text(POI_STANDARD)
        assert "历史建筑" in result

    def test_standard_line_no_coordinates(self):
        result = compress_poi_text(POI_STANDARD)
        # 坐标被去除
        assert "116.3972" not in result
        assert "39.9179" not in result

    def test_missing_type_field_does_not_crash(self):
        result = compress_poi_text(POI_NO_TYPE)
        assert "颐和园" in result
        assert "★4.7" in result

    def test_unparseable_line_returns_original(self):
        result = compress_poi_text(POI_UNPARSEABLE)
        assert result.strip() == POI_UNPARSEABLE.strip()

    def test_multiline_text_produces_multiple_lines(self):
        multi = f"{POI_STANDARD}\n{POI_NO_TYPE}"
        result = compress_poi_text(multi)
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 2

    def test_empty_text_returns_empty(self):
        assert compress_poi_text("") == ""

    def test_compression_reduces_length(self):
        result = compress_poi_text(POI_STANDARD)
        assert len(result) < len(POI_STANDARD)


# ── 天气压缩测试 ──────────────────────────────────────────────────────────────

class TestCompressWeather:
    def test_standard_line_date_format(self):
        result = compress_weather_text(WEATHER_STANDARD)
        assert "08-01" in result
        # 完整年份去除
        assert "2025" not in result

    def test_standard_line_temperature(self):
        result = compress_weather_text(WEATHER_STANDARD)
        assert "32/22℃" in result

    def test_standard_line_weather_condition(self):
        result = compress_weather_text(WEATHER_STANDARD)
        assert "晴/晴" in result

    def test_standard_line_wind(self):
        result = compress_weather_text(WEATHER_STANDARD)
        assert "南风 2级" in result

    def test_no_wind_field_does_not_crash(self):
        result = compress_weather_text(WEATHER_NO_WIND)
        assert "08-02" in result
        assert "28/20℃" in result

    def test_unparseable_line_returns_original(self):
        result = compress_weather_text(WEATHER_UNPARSEABLE)
        assert result.strip() == WEATHER_UNPARSEABLE.strip()

    def test_compression_reduces_length(self):
        result = compress_weather_text(WEATHER_STANDARD)
        assert len(result) < len(WEATHER_STANDARD)


# ── 统一入口测试 ──────────────────────────────────────────────────────────────

class TestCompressAgentResponses:
    def test_all_four_responses_returned(self):
        a, w, h, f = compress_agent_responses(
            POI_STANDARD, WEATHER_STANDARD, POI_NO_TYPE, POI_STANDARD
        )
        assert a and w and h and f

    def test_attraction_compressed(self):
        a, _, _, _ = compress_agent_responses(POI_STANDARD, "", "", "")
        assert len(a) < len(POI_STANDARD)

    def test_weather_compressed(self):
        _, w, _, _ = compress_agent_responses("", WEATHER_STANDARD, "", "")
        assert len(w) < len(WEATHER_STANDARD)

    def test_compression_error_falls_back_to_original(self, monkeypatch):
        """压缩器内部错误时应静默回退到原始文本，不上抛异常。"""
        import app.agents.compressor as mod

        def _boom(text):
            raise RuntimeError("模拟压缩错误")

        monkeypatch.setattr(mod, "compress_poi_text", _boom)
        monkeypatch.setattr(mod, "compress_weather_text", _boom)

        a, w, h, f = mod.compress_agent_responses(
            POI_STANDARD, WEATHER_STANDARD, POI_NO_TYPE, POI_STANDARD
        )
        # 应回退到原始文本
        assert a == POI_STANDARD
        assert w == WEATHER_STANDARD

    def test_empty_inputs_return_empty(self):
        a, w, h, f = compress_agent_responses("", "", "", "")
        assert a == "" and w == "" and h == "" and f == ""
