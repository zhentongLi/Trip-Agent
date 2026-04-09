"""Skill Router：根据 skill 名称执行对应能力。"""

from __future__ import annotations

from typing import Any, Dict

from .registry import SkillRegistry


class SkillRouter:
    """统一 Skill 路由器。"""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    async def dispatch(self, skill_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._registry.get(skill_name)
        return await skill.run(payload)
