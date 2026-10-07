# -*- coding: utf-8 -*-
"""工具注册：汇总所有工具 + 导出 LangChain Tool 列表。"""
from .notes import add_note, search_notes
from .reminder import add_reminder, delete_reminder, list_reminder_history, list_reminders
from .schedule import add_schedule, delete_schedule, list_schedules
from .time_tool import get_current_time
from .todo import add_todo, complete_todo, list_todos
from .weather import get_weather

# LangGraph / ChatOpenAI.bind_tools 使用的工具列表
TOOLS = [
    get_current_time,
    get_weather,
    add_todo,
    list_todos,
    complete_todo,
    add_schedule,
    list_schedules,
    delete_schedule,
    add_reminder,
    list_reminders,
    delete_reminder,
    list_reminder_history,
    search_notes,
    add_note,
]

# 工具的中文显示名（页面展示用，函数名保持英文）
TOOL_DISPLAY = {
    "get_current_time": "当前时间",
    "get_weather": "天气查询",
    "add_todo": "添加待办",
    "list_todos": "待办列表",
    "complete_todo": "完成待办",
    "add_schedule": "添加日程",
    "list_schedules": "日程列表",
    "delete_schedule": "删除日程",
    "add_reminder": "设置提醒",
    "list_reminders": "提醒列表",
    "delete_reminder": "取消提醒",
    "list_reminder_history": "提醒记录",
    "search_notes": "笔记检索",
    "add_note": "保存笔记",
}

# 工具分组（左侧栏展示用）：组名 -> 工具名列表
TOOL_GROUPS = [
    ("常用查询", ["get_current_time", "get_weather"]),
    ("待办", ["add_todo", "list_todos", "complete_todo"]),
    ("日程", ["add_schedule", "list_schedules", "delete_schedule"]),
    ("提醒", ["add_reminder", "list_reminders", "delete_reminder", "list_reminder_history"]),
    ("笔记", ["search_notes", "add_note"]),
]

# 每个工具的快捷示例（左侧栏展示用）
TOOL_EXAMPLES = {
    "get_current_time": "现在几点？",
    "get_weather": "大连今天天气怎么样？",
    "add_todo": "帮我记个待办：周五之前交周报",
    "list_todos": "我的待办有哪些？",
    "complete_todo": "把待办里那条'交周报'标为完成",
    "add_schedule": "帮我安排明天下午3点的项目评审会",
    "list_schedules": "我最近有什么日程？",
    "delete_schedule": "帮我把日程里的'项目评审会'删掉",
    "add_reminder": "提醒我2分钟后喝水",
    "list_reminders": "我有哪些提醒？",
    "delete_reminder": "取消'喝水'那条提醒",
    "list_reminder_history": "我之前设置过哪些提醒？",
    "search_notes": "查我的笔记里关于LangGraph的内容",
    "add_note": "帮我记一条笔记：今天学了LangGraph的图编排",
}

# 工具名 → 可调用对象（供 tools 节点执行）
TOOL_MAP = {t.name: t for t in TOOLS}

__all__ = ["TOOLS", "TOOL_MAP"]
