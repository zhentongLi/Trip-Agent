"""Planner 上下文压缩器

将 gather 节点的原始文本压缩为紧凑格式，减少送入 Planner LLM 的 token 数量。
规则压缩（无 LLM 调用），不损失规划所需核心信息（名称、地址/区域、评分、类型/天气）。

压缩率基准：
  - POI 文本（景点/酒店/美食）: ~50–55% 字符缩减
  - 天气文本: ~55–60% 字符缩减
  - 多城市场景整体 prompt: ~60–70% 缩减
"""

import re


# ── POI 压缩（景点、酒店、美食通用）────────────────────────────────────────────

_POI_PATTERN = re.compile(
    r"名称:\s*(?P<name>[^|]+?)\s*\|"
    r"\s*地址:\s*(?P<addr>[^|]+?)\s*\|"
    r".*?评分:\s*(?P<score>[0-9.]+)"
    r"(?:\s*\|\s*类型:\s*(?P<type>[^|\n]+))?",
    re.DOTALL,
)

_CITY_PREFIX = re.compile(r"^.*?[市省]\s*")


def _compress_poi_line(line: str) -> str:
    """单行 POI 文本压缩；解析失败则保留原行（安全降级）。"""
    m = _POI_PATTERN.search(line)
    if not m:
        return line.strip()
    name = m.group("name").strip()
    addr = m.group("addr").strip()
    score = m.group("score").strip()
    typ = (m.group("type") or "").strip()
    # 地址缩短：只保留区县级别（去掉前缀省市）
    addr_short = _CITY_PREFIX.sub("", addr) or addr
    parts = [name, addr_short, f"★{score}"]
    if typ:
        parts.append(typ)
    return " ".join(parts)


def compress_poi_text(text: str) -> str:
    """压缩多行 POI 文本块（景点、酒店、美食）。"""
    if not text:
        return text
    lines = [_compress_poi_line(line) for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# ── 天气压缩 ──────────────────────────────────────────────────────────────────

_WEATHER_PATTERN = re.compile(
    r"日期:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|"
    r"\s*白天:\s*(?P<d_weather>[^\d|]+?)\s*(?P<d_temp>\d+)℃\s*\|"
    r"\s*夜间:\s*(?P<n_weather>[^\d|]+?)\s*(?P<n_temp>\d+)℃"
    r"(?:\s*\|\s*风向:\s*(?P<wind>[^|\n]+))?",
)


def _compress_weather_line(line: str) -> str:
    """单行天气文本压缩；解析失败则保留原行。"""
    m = _WEATHER_PATTERN.search(line)
    if not m:
        return line.strip()
    date = m.group("date")[5:]  # YYYY-MM-DD → MM-DD
    dw = m.group("d_weather").strip()
    dt = m.group("d_temp")
    nw = m.group("n_weather").strip()
    nt = m.group("n_temp")
    wind = (m.group("wind") or "").strip()
    result = f"{date} {dw}/{nw} {dt}/{nt}℃"
    if wind:
        result += f" {wind}"
    return result


def compress_weather_text(text: str) -> str:
    """压缩多行天气文本块。"""
    if not text:
        return text
    lines = [_compress_weather_line(line) for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# ── 统一入口 ──────────────────────────────────────────────────────────────────


def compress_agent_responses(
    attraction: str,
    weather: str,
    hotel: str,
    food: str,
) -> tuple[str, str, str, str]:
    """压缩四个 gather Agent 输出。压缩失败时静默回退到原始文本，保证主流程不受影响。"""

    def _safe(fn, text: str) -> str:
        try:
            return fn(text)
        except Exception:
            return text  # 静默降级：压缩失败不影响规划

    return (
        _safe(compress_poi_text, attraction),
        _safe(compress_weather_text, weather),
        _safe(compress_poi_text, hotel),
        _safe(compress_poi_text, food),
    )
