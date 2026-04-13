"""导游问答 Skill。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from loguru import logger

from ..services.memory_service import get_memory_service
from ..services.rag_service import get_guide_rag_service
from .base import RuntimeSkill

# GuideQASkill 封装了基于 RAG 的导游问答能力，继承自 RuntimeSkill。
class GuideQASkill(RuntimeSkill):
    """封装导游问答 RAG 能力。"""

    # Skill 的名称和描述，供注册中心使用
    name = "guide_qa"
    description = "基于 RAG 的导游问答能力"

    # async 版本的 run 方法，内部调用同步的 RAGService.ask 方法
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

        """
            获取 RAGService 实例，并调用 ask 方法获取答案和参考文献,使用 asyncio.to_thread 将同步方法包装成异步调用，避免在 RAGService 内部引入异步复杂度，并且 RAGService 内部可能有同步的 ChromaDB 调用
        """
        service = get_guide_rag_service()
        memory = get_memory_service()
        memory_context = await memory.async_build_context(session_id)

        result = await asyncio.to_thread(
            service.ask,
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

        await memory.async_record_turn(
            session_id=session_id,
            user_message=question,
            assistant_message=result.get("answer", ""),
            city=city,
            attraction_name=attraction_name,
        )

        return result
