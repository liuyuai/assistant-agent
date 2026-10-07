# -*- coding: utf-8 -*-
"""日程管理工具（JSON 文件存储）。"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from langchain_core.tools import tool

_DATA = Path(__file__).resolve().parents[2] / "data" / "schedules.json"


def _load() -> list[dict]:
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def _save(items: list[dict]) -> None:
    _DATA.parent.mkdir(exist_ok=True)
    _DATA.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@tool
def add_schedule(title: str, time_str: str) -> str:
    """添加一条日程。参数 time_str 是 ISO 格式时间字符串，例如"2026-10-10 14:00:00"。

    调用前先把用户口语时间换算成具体的 ISO 时间（需要时先查当前时间）。
    """
    items = _load()
    item = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "time": time_str,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(item)
    items.sort(key=lambda x: x["time"])
    _save(items)
    return f"已添加日程：{title} @ {time_str}"


@tool
def list_schedules() -> str:
    """列出所有日程（按时间排序）。"""
    items = _load()
    if not items:
        return "当前没有日程。"
    lines = [f"{i}. [{it['id']}] {it['time']}  {it['title']}" for i, it in enumerate(items, 1)]
    return "日程列表：\n" + "\n".join(lines)


@tool
def delete_schedule(schedule_id: str) -> str:
    """删除一条日程。参数 schedule_id 是日程的 id（来自 list_schedules 返回的 [id]）。"""
    items = _load()
    for it in items:
        if it["id"] == schedule_id:
            items.remove(it)
            _save(items)
            return f"已删除日程：{it['title']}"
    return f"未找到 id={schedule_id} 的日程。"
