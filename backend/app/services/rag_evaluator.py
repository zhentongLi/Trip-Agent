"""RAG 检索评估模块

指标说明：
- Hit@K     召回率：top-K 结果中是否包含至少一个相关文档
- MRR       Mean Reciprocal Rank：第一个相关文档排名的倒数均值，衡量排序质量
- P@K       Precision@K：top-K 结果中相关文档的比例

使用方式：
    python -m backend.tests.evaluate_rag
    或直接运行：
    cd backend && conda run -n trip-agent python tests/evaluate_rag.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────── 单条指标计算 ───────────────────────────

def hit_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """召回率 Hit@K：top-K 内是否命中至少一个相关文档。"""
    top_k = retrieved_ids[:k]
    return 1.0 if any(doc_id in relevant_ids for doc_id in top_k) else 0.0


def precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """精确率 P@K：top-K 内相关文档的比例。"""
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / k


def reciprocal_rank(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """单条 MRR 分量：第一个相关文档排名的倒数（未命中返回 0）。"""
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """NDCG@K：排序增益，越靠前的相关文档得分越高。"""
    def dcg(ids: List[str]) -> float:
        return sum(
            (1.0 / math.log2(i + 2))
            for i, doc_id in enumerate(ids[:k])
            if doc_id in relevant_ids
        )

    actual_dcg = dcg(retrieved_ids)
    ideal_ids = [r for r in retrieved_ids if r in relevant_ids] + \
                [r for r in relevant_ids if r not in retrieved_ids]
    ideal_dcg = dcg(ideal_ids)
    return actual_dcg / ideal_dcg if ideal_dcg > 0 else 0.0


# ─────────────────────────── 评估运行器 ────────────────────────────

def run_eval(
    service,
    eval_dataset: List[Dict[str, Any]],
    k_values: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    对 GuideRAGService 实例运行全量评测。

    Args:
        service: GuideRAGService 实例
        eval_dataset: 评测数据列表，每条格式：
            {
                "id": str,
                "question": str,
                "city": str,
                "attraction_name": str,
                "relevant_doc_ids": List[str]
            }
        k_values: 评测的 K 值列表，默认 [1, 3, 5]

    Returns:
        包含各指标均值和每条详情的结果字典
    """
    if k_values is None:
        k_values = [1, 3, 5]

    results_per_item: List[Dict[str, Any]] = []

    for item in eval_dataset:
        question = item["question"]
        city = item.get("city", "")
        attraction_name = item.get("attraction_name", "")
        relevant_ids = item["relevant_doc_ids"]

        # 调用检索（不走 LLM 生成，只评估召回）
        try:
            refs = service.retrieve(
                question=question,
                city=city,
                attraction_name=attraction_name,
                trip_plan=None,
                top_k=max(k_values),
            )
        except Exception as e:
            results_per_item.append({
                "id": item["id"],
                "question": question,
                "error": str(e),
            })
            continue

        retrieved_ids = [ref.get("doc_id", "") for ref in refs if ref.get("doc_id")]

        item_result: Dict[str, Any] = {
            "id": item["id"],
            "question": question,
            "relevant_ids": relevant_ids,
            "retrieved_ids": retrieved_ids,
            "mrr": reciprocal_rank(retrieved_ids, relevant_ids),
        }
        for k in k_values:
            item_result[f"hit@{k}"] = hit_at_k(retrieved_ids, relevant_ids, k)
            item_result[f"p@{k}"] = precision_at_k(retrieved_ids, relevant_ids, k)
            item_result[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, relevant_ids, k)

        results_per_item.append(item_result)

    # 过滤掉出错的条目
    valid = [r for r in results_per_item if "error" not in r]
    n = len(valid)

    if n == 0:
        return {"error": "所有评测条目均失败", "details": results_per_item}

    # 汇总均值
    summary: Dict[str, Any] = {"n": n, "k_values": k_values}
    summary["mrr"] = round(sum(r["mrr"] for r in valid) / n, 4)
    for k in k_values:
        summary[f"hit@{k}"] = round(sum(r[f"hit@{k}"] for r in valid) / n, 4)
        summary[f"p@{k}"] = round(sum(r[f"p@{k}"] for r in valid) / n, 4)
        summary[f"ndcg@{k}"] = round(sum(r[f"ndcg@{k}"] for r in valid) / n, 4)

    return {"summary": summary, "details": results_per_item}


def load_eval_dataset(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """加载评测数据集，默认读取 backend/data/rag_eval_dataset.json。"""
    if path is None:
        path = Path(__file__).parent.parent.parent / "data" / "rag_eval_dataset.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))
