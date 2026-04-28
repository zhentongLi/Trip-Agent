"""Skill 基类定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class RuntimeSkill(ABC):
    """运行时 Skill 抽象基类。

    子类必须设置类级别属性：
        name (str):        Skill 唯一标识符，注册时用作 Key。
        description (str): 对人可读的 Skill 功能描述，暴露到 /api/skills。

    子类必须实现：
        run(payload) -> Dict:  接受参数字典，返回结果字典。
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Skill。

        Args:
            payload: 路由层传入的参数字典。

        Returns:
            Skill 输出数据（必须是可序列化的字典）。
        """
        raise NotImplementedError

    def metadata(self) -> Dict[str, str]:
        """返回 Skill 的自描述元数据，供 /api/skills 发现接口使用。"""
        return {
            "name": self.name,
            "description": self.description,
        }
