# -*- coding: utf-8 -*-
"""当前时间工具。"""
from __future__ import annotations

import time
from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """获取当前日期和时间，格式：YYYY-MM-DD HH:MM:SS（星期几）。"""
    now = datetime.now()
    weeks = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return now.strftime("%Y-%m-%d %H:%M:%S") + " " + weeks[now.weekday()]
