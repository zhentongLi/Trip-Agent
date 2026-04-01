"""
RAG 召回质量评估脚本

运行方式：
    cd backend
    conda run -n trip-agent python tests/evaluate_rag.py
    conda run -n trip-agent python tests/evaluate_rag.py --k 1 3 5 10
    conda run -n trip-agent python tests/evaluate_rag.py --output results.json

输出示例：
    ┌────────────────────────────────┐
    │   RAG 检索评估报告  (n=15)      │
    ├────────┬──────┬──────┬────────┤
    │ 指标   │  @1  │  @3  │  @5    │
    ├────────┼──────┼──────┼────────┤
    │ Hit    │ 0.73 │ 0.87 │ 0.93   │
    │ P@K    │ 0.73 │ 0.42 │ 0.29   │
    │ NDCG   │ 0.73 │ 0.79 │ 0.82   │
    ├────────┴──────┴──────┴────────┤
    │ MRR: 0.78                      │
    └────────────────────────────────┘
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 将 backend/ 加入 sys.path，支持直接运行
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag_service import GuideRAGService
from app.services.rag_evaluator import run_eval, load_eval_dataset


def _color(text: str, code: str) -> str:
    """终端着色（仅在 TTY 下生效）。"""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def _score_color(v: float) -> str:
    if v >= 0.8:
        return _color(f"{v:.4f}", "32")   # 绿
    if v >= 0.5:
        return _color(f"{v:.4f}", "33")   # 黄
    return _color(f"{v:.4f}", "31")       # 红


def print_report(result: dict, k_values: list[int]) -> None:
    summary = result.get("summary", {})
    details = result.get("details", [])
    n = summary.get("n", 0)

    sep = "─" * 52
    print(f"\n{sep}")
    print(f"  RAG 检索评估报告  (n={n} 条有效评测)")
    print(sep)

    # 表头
    header = f"  {'指标':<8}" + "".join(f"  @{k:<5}" for k in k_values)
    print(header)
    print("  " + "─" * 48)

    for metric, label in [("hit", "Hit@K"), ("p", "P@K"), ("ndcg", "NDCG@K")]:
        row = f"  {label:<8}" + "".join(
            f"  {_score_color(summary.get(f'{metric}@{k}', 0)):<14}"
            for k in k_values
        )
        print(row)

    print("  " + "─" * 48)
    print(f"  MRR: {_score_color(summary.get('mrr', 0))}")
    print(sep)

    # 失败/低分详情
    failed = [d for d in details if "error" in d]
    low_hit = [
        d for d in details
        if "error" not in d and d.get(f"hit@{k_values[-1]}", 1.0) == 0.0
    ]

    if failed:
        print(f"\n  {_color('❌ 失败条目', '31')} ({len(failed)}条):")
        for d in failed:
            print(f"    [{d['id']}] {d['question'][:40]} → {d['error'][:60]}")

    if low_hit:
        print(f"\n  {_color('⚠️  未命中条目', '33')} (top-{k_values[-1]} 内未找到相关文档):")
        for d in low_hit:
            print(f"    [{d['id']}] {d['question'][:40]}")
            print(f"         相关: {d['relevant_ids']}")
            print(f"         召回: {d['retrieved_ids'][:k_values[-1]]}")

    print()


def main():
    parser = argparse.ArgumentParser(description="评估 RAG 召回质量")
    parser.add_argument(
        "--k", nargs="+", type=int, default=[1, 3, 5],
        help="评测的 K 值，默认: 1 3 5",
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="评测数据集路径，默认使用 data/rag_eval_dataset.json",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="将详细结果输出到 JSON 文件",
    )
    args = parser.parse_args()

    print("正在初始化 RAG 服务...")
    service = GuideRAGService()

    print("加载评测数据集...")
    dataset = load_eval_dataset(args.dataset)
    print(f"共 {len(dataset)} 条评测样本")

    print("开始评测（仅检索，不调用 LLM 生成）...")
    result = run_eval(service, dataset, k_values=sorted(set(args.k)))

    if "error" in result:
        print(f"评测失败: {result['error']}")
        sys.exit(1)

    print_report(result, sorted(set(args.k)))

    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"详细结果已写入: {args.output}")


if __name__ == "__main__":
    main()
