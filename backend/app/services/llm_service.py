"""LLM服务模块 - 基于 LangChain ChatOpenAI"""

import os
from loguru import logger
from langchain_openai import ChatOpenAI
from ..config import get_settings

# 全局LLM实例
_llm_instance = None


def get_llm() -> ChatOpenAI:
    """
    获取LLM实例(单例模式)

    兼容 HelloAgents 风格的 LLM_* 环境变量和标准 OPENAI_* 环境变量，
    LLM_* 优先级高于 OPENAI_*，便于无缝切换。

    Returns:
        ChatOpenAI 实例
    """
    global _llm_instance

    if _llm_instance is None:
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

        _llm_instance = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

        logger.success(f"✅ LLM服务初始化成功 | model={model} | base_url={base_url}")

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None

