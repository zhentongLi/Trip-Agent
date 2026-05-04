"""Agent 响应预处理：质量过滤 + 精确去重 + 相似去重

对应用户提供的 preprocessResults 三步逻辑，用 Python 实现：
  1. 质量过滤  — 含失败占位词或过短 → 丢弃
  2. 精确去重  — MD5 hash 完全相同 → 保留第一条
  3. 相似去重  — Jaccard > threshold → 保留第一条
"""

from __future__ import annotations

import hashlib
import re
from typing import List

# 触发质量过滤的失败占位词（中英文）
_FAILURE_PATTERNS: tuple[str, ...] = (
    "暂无", "未找到", "无法访问", "暂时无法", "没有找到",
    "抱歉，", "查询失败", "获取失败", "无数据",
    "unable to retrieve", "failed to fetch", "no information available",
)

_MIN_LEN = 20  # 少于此字符数视为无效响应


# ── 内部工具 ────────────────────────────────────────────────────────────────


def _hash(text: str) -> str:
    return hashlib.md5(text.strip().encode()).hexdigest()


def _tokenize(text: str) -> frozenset[str]:
    """按单词边界分词，支持中文字符（每个汉字视为独立 token）"""
    return frozenset(re.findall(r"[\w一-鿿]+", text))


def _jaccard(a: str, b: str) -> float:
    sa, sb = _tokenize(a), _tokenize(b)
    union = len(sa | sb)
    return len(sa & sb) / union if union else 0.0


# ── 公开接口 ────────────────────────────────────────────────────────────────


def is_valid_response(text: str) -> bool:
    """质量过滤：非空、长度充足、不含失败占位词"""
    if not text or len(text.strip()) < _MIN_LEN:
        return False
    return not any(pat in text for pat in _FAILURE_PATTERNS)


def preprocess_responses(
    responses: List[str],
    jaccard_threshold: float = 0.85,
) -> List[str]:
    """三步预处理，对应 preprocessResults 逻辑。

    Args:
        responses: 原始 Agent 响应列表
        jaccard_threshold: 相似度阈值，超过则视为重复

    Returns:
        过滤 + 去重后的有效响应列表
    """
    # Step 1: 质量过滤
    valid = [r for r in responses if is_valid_response(r)]

    # Step 2: 精确去重（hash）
    seen: set[str] = set()
    exact: List[str] = []
    for r in valid:
        h = _hash(r)
        if h not in seen:
            seen.add(h)
            exact.append(r)

    # Step 3: 相似去重（Jaccard）
    result: List[str] = []
    for r in exact:
        if not any(_jaccard(r, s) > jaccard_threshold for s in result):
            result.append(r)

    return result
