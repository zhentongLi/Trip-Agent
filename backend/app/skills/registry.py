"""Skill 注册中心。"""

from __future__ import annotations

from typing import Dict, List

from .base import RuntimeSkill


class SkillRegistry:
    """
        维护 Skill 实例注册与查询。
        通过 register 方法注册 Skill 实例，使用 get 方法根据名称查询 Skill。
        使用 list_names 方法可以获取所有已注册 Skill 的名称列表。
    """

    def __init__(self):
        self._skills: Dict[str, RuntimeSkill] = {}

    def register(self, skill: RuntimeSkill) -> None:
        if not skill.name:
            raise ValueError("Skill name 不能为空")
        self._skills[skill.name] = skill

    def get(self, name: str) -> RuntimeSkill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"未找到 Skill: {name}") from exc

    def list_names(self) -> List[str]:
        return sorted(self._skills.keys())
