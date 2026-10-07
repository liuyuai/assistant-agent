# -*- coding: utf-8 -*-
"""意图路由：根据用户最新消息，动态挑选本次该绑定给大模型的工具子集。

为什么做：bind_tools 会把所有工具平铺给模型，工具越多模型选错概率越高。
按意图只绑"命中域的工具 + 基础工具"，模型选择更准。

策略（宁可多绑、不可少绑）：
- 关键词规则命中域 → 该域工具 + 基础工具（时间/天气，供多步推理支撑）
- 命中多个域 → 合并
- 一个都没命中 → 返回全部工具（兜底，保证功能不丢）
"""
from __future__ import annotations

from . import TOOL_MAP, TOOLS

# 意图域 -> 关键词（规则层，命中即认为属于该域）
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "天气": ["天气", "下雨", "气温", "温度", "晴", "多云", "降温", "降雨", "风力", "湿度", "下雪", "weather"],
    "时间": ["几点", "时间", "日期", "现在", "几号", "什么时候", "几点了"],
    "待办": ["待办", "todo", "任务", "备忘", "周报", "交报", "勾掉", "办完"],
    "日程": ["日程", "安排", "会议", "预约", "行程", "聚会", "schedule"],
    "提醒": ["提醒", "叫我", "到点", "定时", "闹钟", "别忘了", "记得提醒", "催我"],
    "笔记": ["笔记", "搜索", "我之前", "记一下", "保存", "note", "rag", "查查"],
}

# 各域包含的工具
_INTENT_TOOLS: dict[str, list[str]] = {
    "天气": ["get_weather"],
    "时间": ["get_current_time"],
    "待办": ["add_todo", "list_todos", "complete_todo"],
    "日程": ["add_schedule", "list_schedules", "delete_schedule"],
    "提醒": ["add_reminder", "list_reminders", "delete_reminder", "list_reminder_history"],
    "笔记": ["search_notes", "add_note"],
}

# 任何场景都可能用到的基础工具（多步推理支撑，如"提醒我明天9点"需先查当前时间）
_BASE_TOOLS = ["get_current_time", "get_weather"]


def select_tools(query: str) -> list:
    """根据用户消息返回本次绑定给大模型的工具子集。"""
    q = (query or "").lower()
    hit_groups = {g for g, kws in _INTENT_KEYWORDS.items() if any(k in q for k in kws)}

    if not hit_groups:
        return TOOLS  # 没命中 → 全部工具，保证能力不丢

    names: list[str] = []
    for g in hit_groups:
        for n in _INTENT_TOOLS[g]:
            if n not in names:
                names.append(n)
    for n in _BASE_TOOLS:  # 基础工具始终带上
        if n not in names:
            names.append(n)

    return [TOOL_MAP[n] for n in names if n in TOOL_MAP]
