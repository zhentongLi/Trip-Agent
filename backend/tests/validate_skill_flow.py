"""Automated validation script for runtime skill flow.

Usage examples:
1) Run both router + API (in-process ASGI):
   conda run -n trip-agent python tests/validate_skill_flow.py --mode all --http-target asgi

2) Run only router dispatch checks:
   conda run -n trip-agent python tests/validate_skill_flow.py --mode router

3) Run API checks against live service:
   conda run -n trip-agent python tests/validate_skill_flow.py --mode api --http-target live --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from httpx import ASGITransport, AsyncClient

# Ensure backend root is in sys.path when executed as a plain script.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.main import app
from app.dependencies import get_skill_router


@dataclass
class CaseResult:
    name: str
    ok: bool
    latency_ms: float
    detail: str


def _sample_cases() -> List[Dict[str, Any]]:
    return [
        {
            "name": "beijing_gugong",
            "question": "第一次去故宫，半天怎么安排路线，避坑点有哪些？",
            "city": "北京",
            "attraction_name": "故宫博物院",
            "top_k": 4,
        },
        {
            "name": "chengdu_food",
            "question": "宽窄巷子附近晚上吃什么更地道？",
            "city": "成都",
            "attraction_name": "宽窄巷子",
            "top_k": 3,
        },
        {
            "name": "hangzhou_west_lake",
            "question": "西湖半日游怎么安排拍照和步行路线？",
            "city": "杭州",
            "attraction_name": "西湖",
            "top_k": 4,
        },
    ]

# 结果校验函数，检查 answer 字段非空，references 是列表且长度合理，每个 reference 包含必要字段。
def _validate_result_shape(obj: Dict[str, Any], top_k: int) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "result is not dict"
    if "answer" not in obj or "references" not in obj:
        return False, "missing required keys: answer/references"

    answer = obj.get("answer") or ""
    refs = obj.get("references")
    if not isinstance(answer, str) or not answer.strip():
        return False, "answer is empty"
    if not isinstance(refs, list):
        return False, "references is not list"
    if len(refs) == 0:
        return False, "references is empty"
    if len(refs) > max(1, top_k):
        return False, f"references too many: {len(refs)} > top_k({top_k})"

    for idx, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            return False, f"reference[{idx}] is not dict"
        for key in ("title", "city", "attraction_name", "snippet", "source", "score"):
            if key not in ref:
                return False, f"reference[{idx}] missing key: {key}"

    return True, "ok"


async def run_router_checks() -> List[CaseResult]:
    results: List[CaseResult] = []
    router = get_skill_router()

    for case in _sample_cases():
        name = case["name"]
        payload = {
            "question": case["question"],
            "city": case["city"],
            "attraction_name": case["attraction_name"],
            "top_k": case["top_k"],
        }

        started = time.perf_counter()
        try:
            data = await router.dispatch("guide_qa", payload)
            ok, detail = _validate_result_shape(data, case["top_k"])
        except Exception as exc:
            ok, detail = False, f"exception: {type(exc).__name__}: {exc}"
        latency = (time.perf_counter() - started) * 1000
        results.append(CaseResult(name=f"router::{name}", ok=ok, latency_ms=latency, detail=detail))

    return results


async def run_api_checks(http_target: str, base_url: str) -> List[CaseResult]:
    results: List[CaseResult] = []

    if http_target == "asgi":
        client_ctx = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    else:
        client_ctx = AsyncClient(base_url=base_url, timeout=60)

    async with client_ctx as client:
        for case in _sample_cases():
            name = case["name"]
            payload = {
                "question": case["question"],
                "city": case["city"],
                "attraction_name": case["attraction_name"],
                "top_k": case["top_k"],
            }

            started = time.perf_counter()
            try:
                resp = await client.post("/api/guide/ask", json=payload)
                if resp.status_code != 200:
                    ok, detail = False, f"http_status={resp.status_code}, body={resp.text[:200]}"
                else:
                    body = resp.json()
                    ok, detail = _validate_result_shape(body, case["top_k"])
                    if ok and body.get("success") is not True:
                        ok, detail = False, "response success != true"
            except Exception as exc:
                ok, detail = False, f"exception: {type(exc).__name__}: {exc}"

            latency = (time.perf_counter() - started) * 1000
            results.append(CaseResult(name=f"api::{name}", ok=ok, latency_ms=latency, detail=detail))

    return results


def _print_report(results: List[CaseResult]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    avg_latency = sum(r.latency_ms for r in results) / total if total else 0.0

    print("\n=== Skill Validation Report ===")
    print(f"total={total} passed={passed} failed={failed} avg_latency_ms={avg_latency:.2f}")
    print("-------------------------------")
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.name} latency={r.latency_ms:.2f}ms detail={r.detail}")


async def _main_async(args: argparse.Namespace) -> int:
    all_results: List[CaseResult] = []

    if args.mode in ("router", "all"):
        all_results.extend(await run_router_checks())

    if args.mode in ("api", "all"):
        all_results.extend(await run_api_checks(args.http_target, args.base_url))

    _print_report(all_results)
    return 0 if all(r.ok for r in all_results) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate skill flow and runtime quality.")
    parser.add_argument("--mode", choices=["router", "api", "all"], default="all")
    parser.add_argument("--http-target", choices=["asgi", "live"], default="asgi")
    parser.add_argument("--base-url", default="http://localhost:8000")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
