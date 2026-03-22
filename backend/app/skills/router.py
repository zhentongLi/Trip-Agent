"""Skill Router：根据 skill 名称执行对应能力。"""

from __future__ import annotations

from typing import Any, Dict

from .guide_qa_skill import GuideQASkill
from .registry import SkillRegistry

# SkillRouter 负责根据 skill 名称路由到对应的 Skill 实例，并调用其 run 方法执行能力。
class SkillRouter:
    """统一 Skill 路由器。"""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    # dispatch 方法根据 skill_name 从注册中心获取对应的 Skill 实例，并调用其 run 方法执行能力，返回结果。
    async def dispatch(self, skill_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._registry.get(skill_name)
        return await skill.run(payload)


_router_instance: SkillRouter | None = None

# get_skill_router 函数提供全局访问 SkillRouter 实例的接口，内部使用单例模式确保只有一个 SkillRouter 实例被创建，并且在创建时注册了 GuideQASkill。
def get_skill_router() -> SkillRouter:
    global _router_instance
    if _router_instance is None:
        registry = SkillRegistry()      # 创建 Skill 注册中心实例
        registry.register(GuideQASkill())   # 注册 GuideQASkill 实例到注册中心
        _router_instance = SkillRouter(registry)    # 创建 SkillRouter 实例，传入注册中心
    return _router_instance
