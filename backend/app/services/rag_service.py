"""导游 RAG 服务（功能27）"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - openai 可能在部分环境缺失
    OpenAI = None

from ..config import get_settings
from ..models.schemas import TripPlan

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_PATTERN.findall(text or "")]


class GuideRAGService:
    """基于本地知识库检索 + LLM 生成的导游问答服务"""

    def __init__(self):
        backend_dir = Path(__file__).resolve().parents[2]
        self._kb_path = backend_dir / "data" / "guide_knowledge.json"
        self._docs = self._load_docs()
        self._idf = self._build_idf(self._docs)
        self._client = None
        self._model = os.getenv("LLM_MODEL_ID", "gpt-4.1-nano")

    def _load_docs(self) -> List[Dict[str, Any]]:
        if not self._kb_path.exists():
            logger.warning(f"导游知识库不存在: {self._kb_path}")
            return []

        try:
            docs = json.loads(self._kb_path.read_text(encoding="utf-8"))
            norm_docs: List[Dict[str, Any]] = []
            for item in docs:
                norm_docs.append(
                    {
                        "id": str(item.get("id", "")),
                        "title": str(item.get("title", "")),
                        "city": str(item.get("city", "")),
                        "attraction_name": str(item.get("attraction_name", "")),
                        "content": str(item.get("content", "")),
                        "tags": item.get("tags", []) or [],
                        "source": "knowledge_base",
                    }
                )
            logger.success(f"导游知识库加载成功，共 {len(norm_docs)} 条")
            return norm_docs
        except Exception as e:
            logger.error(f"导游知识库加载失败: {e}")
            return []

    @staticmethod
    def _doc_text(doc: Dict[str, Any]) -> str:
        tags = " ".join(doc.get("tags", []))
        return " ".join(
            [
                doc.get("title", ""),
                doc.get("city", ""),
                doc.get("attraction_name", ""),
                doc.get("content", ""),
                tags,
            ]
        )

    def _build_idf(self, docs: List[Dict[str, Any]]) -> Dict[str, float]:
        if not docs:
            return {}
        n_docs = len(docs)
        df_counter: Counter[str] = Counter()
        for doc in docs:
            tokens = set(_tokenize(self._doc_text(doc)))
            df_counter.update(tokens)
        return {
            token: math.log((n_docs + 1) / (freq + 1)) + 1.0
            for token, freq in df_counter.items()
        }

    @staticmethod
    def _trip_plan_docs(trip_plan: Optional[TripPlan]) -> List[Dict[str, Any]]:
        if not trip_plan:
            return []

        docs: List[Dict[str, Any]] = []
        for day in trip_plan.days:
            for attraction in day.attractions:
                docs.append(
                    {
                        "id": f"trip-{day.day_index}-{attraction.name}",
                        "title": f"行程内景点：{attraction.name}",
                        "city": trip_plan.city,
                        "attraction_name": attraction.name,
                        "content": " ".join(
                            [
                                attraction.description or "",
                                f"地址：{attraction.address or ''}",
                                f"建议游览时长：{attraction.visit_duration}分钟",
                                f"预计门票：{attraction.ticket_price or 0}元",
                            ]
                        ),
                        "tags": ["trip_plan", "attraction"],
                        "source": "trip_plan",
                    }
                )
        return docs

    def _score_doc(
        self,
        query_tokens: List[str],
        doc: Dict[str, Any],
        city: str,
        attraction_name: str,
    ) -> float:
        if not query_tokens:
            return 0.0

        doc_text = self._doc_text(doc)
        doc_tokens = _tokenize(doc_text)
        if not doc_tokens:
            return 0.0

        tf = Counter(doc_tokens)
        score = 0.0
        for token in query_tokens:
            token_tf = tf.get(token, 0)
            if token_tf <= 0:
                continue
            idf = self._idf.get(token, 1.0)
            score += (1.0 + math.log(token_tf)) * idf

        q_set = set(query_tokens)
        overlap = len(q_set.intersection(set(doc_tokens)))
        score += overlap * 0.2

        city = (city or "").strip()
        doc_city = (doc.get("city") or "").strip()
        if city:
            if doc_city == city:
                score += 1.5
            elif city in doc_text:
                score += 0.6

        attraction_name = (attraction_name or "").strip()
        if attraction_name:
            if attraction_name == (doc.get("attraction_name") or ""):
                score += 2.0
            elif attraction_name in doc_text:
                score += 0.9

        return score

    def retrieve(
        self,
        question: str,
        city: str = "",
        attraction_name: str = "",
        trip_plan: Optional[TripPlan] = None,
        top_k: int = 4,
    ) -> List[Dict[str, Any]]:
        all_docs = self._docs + self._trip_plan_docs(trip_plan)
        query = " ".join([question or "", city or "", attraction_name or ""])
        query_tokens = _tokenize(query)

        scored: List[tuple[float, Dict[str, Any]]] = []
        for doc in all_docs:
            score = self._score_doc(query_tokens, doc, city, attraction_name)
            if score > 0.05:
                scored.append((score, doc))

        if not scored:
            fallback = [doc for doc in all_docs if city and doc.get("city") == city][:top_k]
            scored = [(0.1, doc) for doc in fallback] if fallback else []

        scored.sort(key=lambda x: x[0], reverse=True)

        references: List[Dict[str, Any]] = []
        for score, doc in scored[:top_k]:
            content = doc.get("content", "")
            references.append(
                {
                    "title": doc.get("title", ""),
                    "city": doc.get("city", ""),
                    "attraction_name": doc.get("attraction_name", ""),
                    "snippet": content[:180],
                    "source": doc.get("source", "knowledge_base"),
                    "score": round(score, 4),
                }
            )
        return references

    def _get_client(self):
        if self._client is not None:
            return self._client

        if OpenAI is None:
            return None

        settings = get_settings()
        api_key = os.getenv("LLM_API_KEY") or settings.openai_api_key
        base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url
        self._model = os.getenv("LLM_MODEL_ID") or settings.openai_model or "gpt-4.1-nano"
        timeout_s = int(os.getenv("LLM_TIMEOUT", "120"))

        if not api_key:
            logger.warning("未配置 LLM_API_KEY，导游问答将使用检索兜底模式")
            return None

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        return self._client

    def _fallback_answer(
        self,
        question: str,
        references: List[Dict[str, Any]],
        city: str,
        attraction_name: str,
    ) -> str:
        if not references:
            target_city = city or "该城市"
            return (
                f"暂时没有命中足够的本地资料来回答“{question}”。\n"
                f"建议你在 {target_city} 的官方景区公众号或文旅局公告中确认最新开放时间和预约规则。"
            )

        lines = ["根据已检索到的资料，给你一个实用版导览建议："]
        for idx, ref in enumerate(references[:3], start=1):
            spot = ref.get("attraction_name") or attraction_name or "该景点"
            lines.append(f"{idx}. {spot}：{ref.get('snippet', '')}")

        lines.append("建议：优先早到、避开中午高峰，并预留机动时间处理排队或天气变化。")
        return "\n".join(lines)

    def generate_answer(
        self,
        question: str,
        references: List[Dict[str, Any]],
        city: str,
        attraction_name: str,
    ) -> str:
        context_blocks: List[str] = []
        for idx, ref in enumerate(references, start=1):
            context_blocks.append(
                f"[资料{idx}] 标题:{ref['title']} 城市:{ref['city']} 景点:{ref['attraction_name']} 内容:{ref['snippet']}"
            )

        context_text = "\n".join(context_blocks) if context_blocks else "无可用资料"

        prompt = (
            "你是一个专业旅游导游，请根据给定资料回答用户问题。\n"
            "要求：\n"
            "1. 只基于资料回答，不要编造未出现事实。\n"
            "2. 回答结构尽量包含：亮点、推荐路线/时段、避坑建议。\n"
            "3. 语气自然、简洁，长度控制在180-320字。\n"
            "4. 如果资料不足，要明确说“资料不足”，并给出保守建议。\n\n"
            f"城市上下文：{city or '未提供'}\n"
            f"景点上下文：{attraction_name or '未提供'}\n"
            f"用户问题：{question}\n"
            f"参考资料：\n{context_text}\n"
        )

        client = self._get_client()
        if client is None:
            return self._fallback_answer(question, references, city, attraction_name)

        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是严谨的中文旅游导游助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.35,
                max_tokens=480,
            )
            answer = (resp.choices[0].message.content or "").strip()
            if not answer:
                return self._fallback_answer(question, references, city, attraction_name)
            return answer
        except Exception as e:
            logger.error(f"导游问答 LLM 调用失败: {e}")
            return self._fallback_answer(question, references, city, attraction_name)

    def ask(
        self,
        question: str,
        city: str = "",
        attraction_name: str = "",
        trip_plan: Optional[TripPlan] = None,
        top_k: int = 4,
    ) -> Dict[str, Any]:
        references = self.retrieve(
            question=question,
            city=city,
            attraction_name=attraction_name,
            trip_plan=trip_plan,
            top_k=top_k,
        )
        answer = self.generate_answer(
            question=question,
            references=references,
            city=city,
            attraction_name=attraction_name,
        )
        return {
            "answer": answer,
            "references": references,
        }


_service_instance: Optional[GuideRAGService] = None


def get_guide_rag_service() -> GuideRAGService:
    global _service_instance
    if _service_instance is None:
        _service_instance = GuideRAGService()
    return _service_instance


async def ask_guide_async(
    question: str,
    city: str = "",
    attraction_name: str = "",
    trip_plan: Optional[TripPlan] = None,
    top_k: int = 4,
) -> Dict[str, Any]:
    service = get_guide_rag_service()
    return await asyncio.to_thread(
        service.ask,
        question,
        city,
        attraction_name,
        trip_plan,
        top_k,
    )
