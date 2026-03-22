"""Skill 基类定义。"""

from __future__ import annotations

# 技能基类，定义所有技能的接口规范,abc 模块提供了抽象基类的支持，可以用来定义接口规范
from abc import ABC, abstractmethod
from typing import Any, Dict


class RuntimeSkill(ABC):
    """运行时 Skill 抽象基类。"""

    name: str = ""
    description: str = ""

    # 所有 Skill 都必须实现 run 方法，接受一个字典参数，返回一个字典结果
    # 定义@abstractmethod，强制子类必须实现这个方法
    @abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Skill。

        Args:
            payload: 路由层传入的参数字典。

        Returns:
            Skill 输出数据。
        """
        raise NotImplementedError
