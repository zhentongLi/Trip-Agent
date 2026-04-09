"""LLM服务模块 - 基于 LangChain ChatOpenAI"""

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI
from loguru import logger

from ..config import get_settings


@lru_cache()
def get_llm() -> ChatOpenAI:
    """获取 LLM 实例（进程级单例，使用 lru_cache）

    兼容 HelloAgents 风格的 LLM_* 环境变量和标准 OPENAI_* 环境变量，
    LLM_* 优先级高于 OPENAI_*，便于无缝切换。
    """
    settings = get_settings()

    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or settings.openai_api_key
    )
    base_url = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or settings.openai_base_url
    )
    model = (
        os.environ.get("LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or settings.openai_model
    )

    instance = ChatOpenAI(model=model, api_key=api_key, base_url=base_url)
    logger.success(f"✅ LLM服务初始化成功 | model={model} | base_url={base_url}")
    return instance


def reset_llm() -> None:
    """重置 LLM 缓存（仅供测试使用）"""
    get_llm.cache_clear()
