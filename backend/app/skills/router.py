"""Skill Router：根据 skill 名称执行对应能力。"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from ..errors import SkillExecutionError, SkillNotFoundError
from .registry import SkillRegistry


class SkillRouter:
    """统一 Skill 路由器。

    - dispatch(): 按名称路由到对应 Skill，统一捕获并包装异常。
    - list_skills(): 暴露所有已注册 Skill 的元数据，供 /api/skills 使用。
    """

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    async def dispatch(self, skill_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行指定 Skill，统一错误处理。

        Raises:
            SkillNotFoundError: Skill 不存在。
            SkillExecutionError: Skill 执行过程中出现异常。
        """
        try:
            skill = self._registry.get(skill_name)
        except KeyError:
            raise SkillNotFoundError(skill_name)

        try:
            return await skill.run(payload)
        except (SkillNotFoundError, SkillExecutionError):
            raise
        except Exception as exc:
            logger.error(
                "❌ Skill '{}' 执行失败: {} — {}",
                skill_name,
                type(exc).__name__,
                exc,
            )
            raise SkillExecutionError(
                skill_name=skill_name,
                message=str(exc),
                original_error=exc,
            ) from exc

    def list_skills(self) -> List[Dict[str, str]]:
        """返回所有已注册 Skill 的元数据列表。"""
        return self._registry.list_skills()
