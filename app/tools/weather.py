# -*- coding: utf-8 -*-
"""天气查询工具：wttr.in 免费 API，失败时降级为模拟数据（明确标注）。"""
from __future__ import annotations

import urllib.parse
import urllib.request

from langchain_core.tools import tool


def _fetch(city: str) -> str | None:
    """调用 wttr.in 获取当前天气文本（无 key 免费接口）。"""
    try:
        q = urllib.parse.quote(city)
        url = f"https://wttr.in/{q}?format=%l:+%c+%t+%w+%h"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return None


@tool
def get_weather(city: str) -> str:
    """查询某个城市的当前天气。参数 city 是城市名，例如"大连"。"""
    real = _fetch(city)
    if real:
        return f"{city} 天气：{real}"
    # 降级：模拟数据（非生产）
    return f"{city} 天气：晴，25°C，东北风3级，湿度45%（模拟数据，接口不可达时使用）"
