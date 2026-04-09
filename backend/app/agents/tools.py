"""高德地图 LangChain 工具工厂

将 AmapRestClient 的方法包装为 LangChain StructuredTool，
供 create_react_agent 的 attraction/weather/hotel/food agent 使用。
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from ..services.amap_rest_client import AmapRestClient


def make_amap_tools(client: AmapRestClient) -> tuple[StructuredTool, StructuredTool]:
    """
    创建 search_places 和 get_weather 两个 StructuredTool。

    Args:
        client: 已初始化的 AmapRestClient（含熔断器）

    Returns:
        (search_places_tool, get_weather_tool)
    """

    def _search_places(keywords: str, city: str) -> str:
        """搜索高德地图兴趣点（景点、酒店、餐厅等），按关键词和城市筛选"""
        return client.search_places(keywords, city)

    def _get_weather(city: str) -> str:
        """查询指定城市的未来几天天气预报"""
        return client.get_weather(city)

    search_places_tool = StructuredTool.from_function(
        func=_search_places,
        name="search_places",
        description="搜索高德地图兴趣点（景点、酒店、餐厅等），按关键词和城市筛选",
    )
    get_weather_tool = StructuredTool.from_function(
        func=_get_weather,
        name="get_weather",
        description="查询指定城市的未来几天天气预报",
    )
    return search_places_tool, get_weather_tool
