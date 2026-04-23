"""导游问答 Skill。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from loguru import logger

from .base import RuntimeSkill


class GuideQASkill(RuntimeSkill):
    """封装导游问答 RAG 能力。

    通过构造函数注入 RAGService 和 MemoryService，
    避免在运行时内部调用全局单例，提升可测试性与解耦程度。
    """

    name = "guide_qa"
    description = "基于 RAG 的导游问答能力，检索本地旅游知识库并结合 LLM 生成景点导览回答"

    def __init__(self, rag_service: Any, memory_service: Any) -> None:
        """
        Args:
            rag_service:    GuideRAGService 实例（提供 ask 方法）。
            memory_service: MemoryService 实例（提供 async_build_context / async_record_turn）。
        """
        self._rag = rag_service
        self._memory = memory_service

    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("question 不能为空")

        session_id = str(payload.get("session_id", "default")).strip() or "default"
        debug = bool(payload.get("debug", False))
        city = str(payload.get("city", ""))
        attraction_name = str(payload.get("attraction_name", ""))
        trip_plan = payload.get("trip_plan")
        top_k = int(payload.get("top_k", 4))

        logger.info(
            "🧩 Skill命中: {} | session_id={} | city={} | attraction={} | top_k={}",
            self.name,
            session_id,
            city or "-",
            attraction_name or "-",
            top_k,
        )

        memory_context = await self._memory.async_build_context(session_id)

        # RAGService 内部有同步 ChromaDB 调用，用 asyncio.to_thread 避免阻塞事件循环
        result = await asyncio.to_thread(
            self._rag.ask,
            question,
            city,
            attraction_name,
            trip_plan,
            top_k,
            memory_context,
        )

        result["skill_meta"] = {
            "skill_name": self.name,
            "skill_description": self.description,
            "session_id": session_id,
            "debug": debug,
        }

        await self._memory.async_record_turn(
            session_id=session_id,
            user_message=question,
            assistant_message=result.get("answer", ""),
            city=city,
            attraction_name=attraction_name,
        )

        return result
