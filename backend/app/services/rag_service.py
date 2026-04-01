"""导游 RAG 服务（功能27）"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import chromadb
except Exception:  # pragma: no cover - chromadb 可能在部分环境缺失
    chromadb = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - openai 可能在部分环境缺失
    OpenAI = None

try:
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover - reranker 可选依赖
    CrossEncoder = None

from ..config import get_settings
from ..models.schemas import TripPlan

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")

def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_PATTERN.findall(text or "")]


class GuideRAGService:
    """基于 Chroma 向量检索 + LLM 生成的导游问答服务"""

    def __init__(self):
        backend_dir = Path(__file__).resolve().parents[2]
        self._kb_path = backend_dir / "data" / "guide_knowledge.json"
        self._chroma_dir = backend_dir / "data" / "chroma_guide"
        self._collection_name = "guide_knowledge"

        self._docs = self._load_docs()

        self._openai_client = None
        self._model = os.getenv("LLM_MODEL_ID", "gpt-4.1-nano")
        self._embed_model = os.getenv("EMBEDDING_MODEL_ID", "text-embedding-3-small")

        # Advanced RAG feature flags
        self._enable_query_rewrite = self._env_bool("RAG_ENABLE_QUERY_REWRITE", True)
        self._enable_multi_query = self._env_bool("RAG_ENABLE_MULTI_QUERY", True)
        self._enable_step_back = self._env_bool("RAG_ENABLE_STEP_BACK", True)
        self._enable_hyde = self._env_bool("RAG_ENABLE_HYDE", False)
        self._enable_rerank = self._env_bool("RAG_ENABLE_RERANK", True)
        self._enable_iterative = self._env_bool("RAG_ENABLE_ITERATIVE", True)

        self._rewrite_max_queries = self._env_int("RAG_REWRITE_MAX_QUERIES", 3, min_value=1, max_value=8)
        self._retrieve_top_k1 = self._env_int("RAG_RETRIEVE_TOP_K1", 24, min_value=4, max_value=100)
        self._iterative_max_rounds = self._env_int("RAG_ITERATIVE_MAX_ROUNDS", 2, min_value=1, max_value=4)
        self._iterative_min_score = self._env_float("RAG_ITERATIVE_MIN_SCORE", 0.45, min_value=0.0, max_value=1.2)

        self._rerank_model_id = os.getenv("RAG_RERANK_MODEL_ID", "BAAI/bge-reranker-v2-m3")
        self._reranker = self._init_reranker()

        self._embedding_strategy = "local_hash"
        self._embedding_dim = 384

        self._chroma_client = None
        self._collection = None

        self._init_embedding_strategy()
        self._init_vector_store()

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _env_int(name: str, default: int, min_value: int = 0, max_value: int = 10_000) -> int:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
            return max(min_value, min(max_value, value))
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float, min_value: float = 0.0, max_value: float = 10.0) -> float:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
            return max(min_value, min(max_value, value))
        except ValueError:
            return default

    def _init_reranker(self):
        if not self._enable_rerank:
            return None
        if CrossEncoder is None:
            logger.warning("未安装 sentence-transformers，Re-ranking 将使用轻量规则重排")
            return None
        try:
            reranker = CrossEncoder(self._rerank_model_id)
            logger.success(f"Cross-Encoder 重排器加载成功: {self._rerank_model_id}")
            return reranker
        except Exception as e:
            logger.warning(f"Cross-Encoder 加载失败，Re-ranking 将使用轻量规则重排: {e}")
            return None

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
                        "tags": [str(t) for t in (item.get("tags", []) or [])],
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

    def _init_embedding_strategy(self) -> None:
        """优先使用远端 embedding；失败时降级到本地哈希向量。"""
        client = self._get_client()
        if client is None:
            logger.warning("未检测到可用 OpenAI 客户端，向量检索将使用本地哈希向量")
            return

        try:
            resp = client.embeddings.create(model=self._embed_model, input=["导游问答向量测试"])
            embedding = resp.data[0].embedding if resp and resp.data else None
            if embedding:
                self._embedding_strategy = "remote"
                self._embedding_dim = len(embedding)
                logger.success(
                    f"向量模型可用，启用远端 embedding | model={self._embed_model} | dim={self._embedding_dim}"
                )
        except Exception as e:
            logger.warning(f"embedding 模型不可用，降级为本地哈希向量: {e}")

    def _init_vector_store(self) -> None:
        if chromadb is None:
            logger.warning("chromadb 未安装，导游检索将退化为关键词匹配")
            return

        try:
            self._chroma_dir.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(self._chroma_dir))

            try:
                self._chroma_client.delete_collection(self._collection_name)
            except Exception:
                pass

            self._collection = self._chroma_client.create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            if not self._docs:
                logger.warning("导游知识库为空，Chroma 索引未写入任何文档")
                return

            ids: List[str] = []
            documents: List[str] = []
            metadatas: List[Dict[str, Any]] = []
            for doc in self._docs:
                ids.append(doc.get("id") or f"doc-{len(ids)}")
                documents.append(self._doc_text(doc))
                metadatas.append(
                    {
                        "title": doc.get("title", ""),
                        "city": doc.get("city", ""),
                        "attraction_name": doc.get("attraction_name", ""),
                        "source": doc.get("source", "knowledge_base"),
                        "snippet": (doc.get("content", "") or "")[:240],
                    }
                )

            embeddings = self._embed_texts(documents)
            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            logger.success(
                f"Chroma 知识库索引构建完成，共 {len(ids)} 条 | strategy={self._embedding_strategy}"
            )
        except Exception as e:
            self._collection = None
            logger.error(f"Chroma 初始化失败，降级为关键词匹配: {e}")

    def _hash_embed(self, text: str) -> List[float]:
        vec = [0.0] * self._embedding_dim
        tokens = _tokenize(text)
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            idx = int(digest, 16) % self._embedding_dim
            vec[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if self._embedding_strategy == "remote":
            client = self._get_client()
            if client is None:
                raise RuntimeError("OpenAI 客户端不可用，无法生成远端 embedding")

            resp = client.embeddings.create(model=self._embed_model, input=texts)
            if not resp or not resp.data:
                raise RuntimeError("embedding 响应为空")
            return [list(item.embedding) for item in resp.data]

        return [self._hash_embed(text) for text in texts]

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

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

    def _retrieve_from_chroma(
        self,
        query: str,
        city: str,
        attraction_name: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if self._collection is None:
            return []

        query_embedding = self._embed_texts([query])[0]
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=max(top_k, 1),
            include=["metadatas", "documents", "distances", "ids"],
        )

        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        chroma_ids = (result.get("ids") or [[]])[0]

        refs: List[Dict[str, Any]] = []
        for idx, md in enumerate(metadatas):
            md = md or {}
            doc_text = documents[idx] if idx < len(documents) else ""
            distance = distances[idx] if idx < len(distances) else 1.0
            base_score = max(0.0, 1.0 - float(distance))

            doc_city = str(md.get("city", ""))
            doc_spot = str(md.get("attraction_name", ""))
            if city and doc_city == city:
                base_score += 0.15
            if attraction_name and doc_spot == attraction_name:
                base_score += 0.2

            refs.append(
                {
                    "doc_id": chroma_ids[idx] if idx < len(chroma_ids) else "",
                    "title": str(md.get("title", "")),
                    "city": doc_city,
                    "attraction_name": doc_spot,
                    "snippet": str(md.get("snippet", "")) or str(doc_text)[:180],
                    "source": str(md.get("source", "knowledge_base")),
                    "score": round(base_score, 4),
                }
            )

        refs.sort(key=lambda x: x["score"], reverse=True)
        return refs

    def _retrieve_trip_plan_refs(
        self,
        query: str,
        city: str,
        attraction_name: str,
        trip_plan: Optional[TripPlan],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        docs = self._trip_plan_docs(trip_plan)
        if not docs:
            return []

        try:
            query_embedding = self._embed_texts([query])[0]
            doc_texts = [self._doc_text(doc) for doc in docs]
            doc_embeddings = self._embed_texts(doc_texts)

            scored: List[tuple[float, Dict[str, Any]]] = []
            for doc, emb in zip(docs, doc_embeddings):
                score = self._cosine_similarity(query_embedding, emb)
                if city and doc.get("city") == city:
                    score += 0.15
                if attraction_name and doc.get("attraction_name") == attraction_name:
                    score += 0.2
                if score > 0.01:
                    scored.append((score, doc))
        except Exception as e:
            logger.warning(f"trip_plan 向量检索失败，改用关键词检索: {e}")
            scored = []
            query_tokens = set(_tokenize(query))
            for doc in docs:
                tokens = set(_tokenize(self._doc_text(doc)))
                overlap = len(query_tokens.intersection(tokens))
                if overlap <= 0:
                    continue
                score = overlap / max(1.0, float(len(query_tokens)))
                if city and doc.get("city") == city:
                    score += 0.15
                if attraction_name and doc.get("attraction_name") == attraction_name:
                    score += 0.2
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        refs: List[Dict[str, Any]] = []
        for score, doc in scored[:top_k]:
            refs.append(
                {
                    "title": doc.get("title", ""),
                    "city": doc.get("city", ""),
                    "attraction_name": doc.get("attraction_name", ""),
                    "snippet": (doc.get("content", "") or "")[:180],
                    "source": "trip_plan",
                    "score": round(float(score), 4),
                }
            )
        return refs

    def _retrieve_keyword_fallback(
        self,
        question: str,
        city: str,
        attraction_name: str,
        trip_plan: Optional[TripPlan],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        all_docs = self._docs + self._trip_plan_docs(trip_plan)
        query_tokens = set(_tokenize(" ".join([question or "", city or "", attraction_name or ""])))

        scored: List[tuple[float, Dict[str, Any]]] = []
        for doc in all_docs:
            tokens = set(_tokenize(self._doc_text(doc)))
            overlap = len(query_tokens.intersection(tokens))
            if overlap <= 0:
                continue
            score = overlap / max(1.0, float(len(query_tokens)))
            if city and doc.get("city") == city:
                score += 0.15
            if attraction_name and doc.get("attraction_name") == attraction_name:
                score += 0.2
            scored.append((score, doc))

        if not scored and city:
            fallback_docs = [doc for doc in all_docs if doc.get("city") == city][:top_k]
            scored = [(0.1, doc) for doc in fallback_docs]

        scored.sort(key=lambda x: x[0], reverse=True)
        refs: List[Dict[str, Any]] = []
        for score, doc in scored[:top_k]:
            refs.append(
                {
                    "doc_id": doc.get("id", ""),
                    "title": doc.get("title", ""),
                    "city": doc.get("city", ""),
                    "attraction_name": doc.get("attraction_name", ""),
                    "snippet": (doc.get("content", "") or "")[:180],
                    "source": doc.get("source", "knowledge_base"),
                    "score": round(float(score), 4),
                }
            )
        return refs

    @staticmethod
    def _unique_texts(items: List[str], max_items: int = 8) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for item in items:
            text = (item or "").strip()
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _extract_json_obj(text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {}
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}

    def _call_multi_query_stepback(
        self,
        client,
        base: str,
        city: str,
        attraction_name: str,
        memory_context: str,
    ) -> List[str]:
        """LLM call 1: Multi-Query + Step-Back 改写，返回生成的查询列表。"""
        generated: List[str] = []
        rewrite_prompt = (
            "你是检索查询改写助手。请基于用户问题输出 JSON："
            '{"queries": ["..."], "step_back": "..."}。\n'
            "规则：queries 最多3条，必须与原问题语义等价但角度不同；"
            "step_back 是一个更抽象、更通用的问题。\n"
            f"城市上下文: {city or '未提供'}\n"
            f"景点上下文: {attraction_name or '未提供'}\n"
            f"用户历史记忆: {memory_context or '无'}\n"
            f"原问题: {base}"
        )
        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是严谨的查询改写助手。"},
                    {"role": "user", "content": rewrite_prompt},
                ],
                temperature=0.2,
                max_tokens=260,
            )
            content = (resp.choices[0].message.content or "").strip()
            obj = self._extract_json_obj(content)
            q_items = obj.get("queries", []) if isinstance(obj, dict) else []
            if isinstance(q_items, list) and self._enable_multi_query:
                generated.extend(str(x) for x in q_items)
            step_back = obj.get("step_back", "") if isinstance(obj, dict) else ""
            if self._enable_step_back and isinstance(step_back, str):
                generated.append(step_back)
        except Exception as e:
            logger.warning(f"Query Rewriting 失败，使用规则改写: {e}")
        return generated

    def _call_hyde(
        self,
        client,
        base: str,
        city: str,
        attraction_name: str,
    ) -> List[str]:
        """LLM call 2: HyDE 改写，返回假设性答案文本列表。"""
        generated: List[str] = []
        hyde_prompt = (
            "请针对下面问题写一段80-140字的假设性答案草稿，用于向量检索，不要编造具体数据。\n"
            f"问题: {base}\n"
            f"上下文: 城市={city or '未提供'} 景点={attraction_name or '未提供'}"
        )
        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是检索增强助手。"},
                    {"role": "user", "content": hyde_prompt},
                ],
                temperature=0.4,
                max_tokens=220,
            )
            hyde_text = (resp.choices[0].message.content or "").strip()
            if hyde_text:
                generated.append(hyde_text)
        except Exception as e:
            logger.warning(f"HyDE 改写失败，已忽略: {e}")
        return generated

    def _rewrite_queries(
        self,
        question: str,
        city: str,
        attraction_name: str,
        memory_context: str = "",
    ) -> List[str]:
        base = (question or "").strip()
        if not base:
            return []

        seeds: List[str] = [base]
        if city and city not in base:
            seeds.append(f"{city} {base}")
        if attraction_name and attraction_name not in base:
            seeds.append(f"{city or ''} {attraction_name} {base}".strip())

        if not self._enable_query_rewrite:
            return self._unique_texts(seeds, max_items=self._rewrite_max_queries)

        client = self._get_client()
        generated: List[str] = []

        run_mq_sb = client is not None and (self._enable_multi_query or self._enable_step_back)
        run_hyde = client is not None and self._enable_hyde

        if run_mq_sb and run_hyde:
            # 两次 LLM 调用互相独立，用线程池并行执行
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_mq = pool.submit(
                    self._call_multi_query_stepback,
                    client, base, city, attraction_name, memory_context,
                )
                fut_hyde = pool.submit(
                    self._call_hyde,
                    client, base, city, attraction_name,
                )
                generated.extend(fut_mq.result())
                generated.extend(fut_hyde.result())
        elif run_mq_sb:
            generated.extend(
                self._call_multi_query_stepback(client, base, city, attraction_name, memory_context)
            )
        elif run_hyde:
            generated.extend(self._call_hyde(client, base, city, attraction_name))

        merged = self._unique_texts(
            [*seeds, *generated],
            max_items=max(self._rewrite_max_queries, 1) + (1 if self._enable_hyde else 0),
        )
        return merged or [base]

    @staticmethod
    def _ref_to_text(ref: Dict[str, Any]) -> str:
        return " ".join(
            [
                str(ref.get("title", "")),
                str(ref.get("city", "")),
                str(ref.get("attraction_name", "")),
                str(ref.get("snippet", "")),
            ]
        )

    def _merge_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        uniq: Dict[str, Dict[str, Any]] = {}
        for ref in candidates:
            key = "|".join(
                [
                    str(ref.get("source", "")),
                    str(ref.get("title", "")),
                    str(ref.get("attraction_name", "")),
                ]
            )
            old = uniq.get(key)
            if old is None or float(ref.get("score", 0.0)) > float(old.get("score", 0.0)):
                uniq[key] = ref

        merged = list(uniq.values())
        merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return merged

    def _rerank_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        # 优先 Cross-Encoder；不可用时退化为轻量重排（融合 lexical + 初始召回分）
        if self._enable_rerank and self._reranker is not None:
            try:
                pairs = [(query, self._ref_to_text(ref)) for ref in candidates]
                scores = self._reranker.predict(pairs)
                reranked: List[Dict[str, Any]] = []
                for ref, score in zip(candidates, scores):
                    item = dict(ref)
                    item["rerank_score"] = round(float(score), 6)
                    reranked.append(item)
                reranked.sort(
                    key=lambda x: (
                        float(x.get("rerank_score", 0.0)),
                        float(x.get("score", 0.0)),
                    ),
                    reverse=True,
                )
                return reranked[:top_k]
            except Exception as e:
                logger.warning(f"Cross-Encoder 重排失败，降级为轻量重排: {e}")

        q_tokens = set(_tokenize(query))
        reranked = []
        for ref in candidates:
            text_tokens = set(_tokenize(self._ref_to_text(ref)))
            overlap = len(q_tokens.intersection(text_tokens))
            lexical_score = overlap / max(1.0, float(len(q_tokens)))
            recall_score = float(ref.get("score", 0.0))
            blended = 0.65 * recall_score + 0.35 * lexical_score
            item = dict(ref)
            item["rerank_score"] = round(blended, 6)
            reranked.append(item)

        reranked.sort(
            key=lambda x: (
                float(x.get("rerank_score", 0.0)),
                float(x.get("score", 0.0)),
            ),
            reverse=True,
        )
        return reranked[:top_k]

    def _need_iterative_retrieval(self, references: List[Dict[str, Any]], top_k: int) -> bool:
        if not references:
            return True
        best = max(
            float(ref.get("rerank_score", ref.get("score", 0.0)))
            for ref in references
        )
        return len(references) < top_k or best < self._iterative_min_score

    def _build_followup_query(
        self,
        question: str,
        references: List[Dict[str, Any]],
        city: str,
        attraction_name: str,
        memory_context: str,
    ) -> str:
        brief_refs = "\\n".join(
            f"- {ref.get('title', '')}: {str(ref.get('snippet', ''))[:80]}"
            for ref in references[:4]
        )
        client = self._get_client()
        if client is None:
            return f"{question} 门票 开放时间 交通 避坑"

        prompt = (
            "你是迭代检索规划助手。请根据原问题和已有检索结果，生成一个新的补充检索query，"
            "用于弥补信息缺口。只输出一句 query，不要解释。\\n"
            f"城市: {city or '未提供'}\\n"
            f"景点: {attraction_name or '未提供'}\\n"
            f"用户记忆: {memory_context or '无'}\\n"
            f"原问题: {question}\\n"
            f"已有资料: \\n{brief_refs or '- 无'}"
        )
        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是严谨的检索规划助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=80,
            )
            query = (resp.choices[0].message.content or "").strip()
            query = query.split("\n", 1)[0].strip()
            return query or f"{question} 门票 开放时间 交通 避坑"
        except Exception as e:
            logger.warning(f"迭代检索 query 生成失败，使用规则 query: {e}")
            return f"{question} 门票 开放时间 交通 避坑"

    @staticmethod
    def _source_counts(references: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for ref in references:
            source = str(ref.get("source", "unknown"))
            counts[source] = counts.get(source, 0) + 1
        return counts

    def retrieve(
        self,
        question: str,
        city: str = "",
        attraction_name: str = "",
        trip_plan: Optional[TripPlan] = None,
        top_k: int = 4,
        memory_context: str = "",
        rewritten_queries: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        queries = rewritten_queries or self._rewrite_queries(
            question=question,
            city=city,
            attraction_name=attraction_name,
            memory_context=memory_context,
        )
        if not queries:
            queries = [question]

        recall_budget = max(top_k * 2, self._retrieve_top_k1)
        per_query_k = max(2, math.ceil(recall_budget / max(1, len(queries))))

        candidates: List[Dict[str, Any]] = []
        for query in queries:
            local_candidates: List[Dict[str, Any]] = []

            if self._collection is not None:
                try:
                    local_candidates.extend(
                        self._retrieve_from_chroma(
                            query=query,
                            city=city,
                            attraction_name=attraction_name,
                            top_k=per_query_k,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Chroma 检索失败，query={query[:40]}: {e}")

            if trip_plan is not None:
                local_candidates.extend(
                    self._retrieve_trip_plan_refs(
                        query=query,
                        city=city,
                        attraction_name=attraction_name,
                        trip_plan=trip_plan,
                        top_k=max(2, per_query_k // 2),
                    )
                )

            if not local_candidates:
                local_candidates = self._retrieve_keyword_fallback(
                    question=query,
                    city=city,
                    attraction_name=attraction_name,
                    trip_plan=trip_plan,
                    top_k=per_query_k,
                )

            candidates.extend(local_candidates)

        merged = self._merge_candidates(candidates)
        return self._rerank_candidates(question, merged, top_k)

    def _get_client(self):
        if self._openai_client is not None:
            return self._openai_client

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

        self._openai_client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        return self._openai_client

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
        memory_context: str = "",
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
            f"用户历史记忆：{memory_context or '无'}\n"
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
        memory_context: str = "",
    ) -> Dict[str, Any]:
        rewritten_queries = self._rewrite_queries(
            question=question,
            city=city,
            attraction_name=attraction_name,
            memory_context=memory_context,
        )
        references = self.retrieve(
            question=question,
            city=city,
            attraction_name=attraction_name,
            trip_plan=trip_plan,
            top_k=max(top_k, 1),
            memory_context=memory_context,
            rewritten_queries=rewritten_queries,
        )

        iterative_rounds = 1
        used_queries = list(rewritten_queries)
        if self._enable_iterative:
            while iterative_rounds < self._iterative_max_rounds and self._need_iterative_retrieval(references, top_k):
                followup_query = self._build_followup_query(
                    question=question,
                    references=references,
                    city=city,
                    attraction_name=attraction_name,
                    memory_context=memory_context,
                )
                if not followup_query:
                    break
                if followup_query.lower() in {q.lower() for q in used_queries}:
                    break

                used_queries.append(followup_query)
                iterative_rounds += 1

                more_refs = self.retrieve(
                    question=question,
                    city=city,
                    attraction_name=attraction_name,
                    trip_plan=trip_plan,
                    top_k=max(top_k * 2, 6),
                    memory_context=memory_context,
                    rewritten_queries=[followup_query],
                )
                references = self._rerank_candidates(
                    question,
                    self._merge_candidates([*references, *more_refs]),
                    top_k,
                )

        answer = self.generate_answer(
            question=question,
            references=references,
            city=city,
            attraction_name=attraction_name,
            memory_context=memory_context,
        )

        source_counts = self._source_counts(references)
        has_local_kb_hit = source_counts.get("knowledge_base", 0) > 0
        reranker_mode = "disabled"
        if self._enable_rerank:
            reranker_mode = "cross_encoder" if self._reranker is not None else "lightweight"

        retrieval_meta = {
            "rewritten_queries": used_queries,
            "iterative_rounds": iterative_rounds,
            "source_counts": source_counts,
            "has_local_kb_hit": has_local_kb_hit,
            "vector_store_enabled": self._collection is not None,
            "embedding_strategy": self._embedding_strategy,
            "reranker_mode": reranker_mode,
        }

        logger.info(
            "🔎 RAG命中 | local_kb_hit={} | source_counts={} | vector_store={} | embed={} | reranker={}",
            has_local_kb_hit,
            source_counts,
            self._collection is not None,
            self._embedding_strategy,
            reranker_mode,
        )

        return {
            "answer": answer,
            "references": references,
            "retrieval_meta": retrieval_meta,
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
    memory_context: str = "",
) -> Dict[str, Any]:
    service = get_guide_rag_service()
    return await asyncio.to_thread(
        service.ask,
        question,
        city,
        attraction_name,
        trip_plan,
        top_k,
        memory_context,
    )
