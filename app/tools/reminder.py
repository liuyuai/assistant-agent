# -*- coding: utf-8 -*-
"""定时提醒：JSON 存储 + 到期检测（调度循环在 server.py 里跑）。

非生产实现：asyncio 轮询 + 文件存储；生产可替换为 APScheduler/Celery + Redis。
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

_DATA = Path(__file__).resolve().parents[2] / "data" / "reminders.json"
_HISTORY = Path(__file__).resolve().parents[2] / "data" / "reminder_history.json"


def _load() -> list[dict]:
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8-sig"))  # 兼容 BOM
        except json.JSONDecodeError:
            return []
    return []


def _save(items: list[dict]) -> None:
    _DATA.parent.mkdir(exist_ok=True)
    _DATA.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@tool
def add_reminder(title: str, time_str: str) -> str:
    """设置一个定时提醒，到点后助手会主动提醒用户。

    参数 time_str 是 ISO 格式时间字符串，例如"2026-10-09 09:00:00"。
    调用前先把用户口语时间（"明天早上9点"）换算成具体 ISO 时间（先查当前时间）。
    """
    try:
        datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return f"时间格式不对（应为 YYYY-MM-DD HH:MM:SS）：{time_str}"
    items = _load()
    item = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "time": time_str,
        "triggered": False,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(item)
    items.sort(key=lambda x: x["time"])
    _save(items)
    return f"已设置提醒：{title} @ {time_str}（提醒 id: {item['id']}）"


@tool
def list_reminders() -> str:
    """列出所有定时提醒及状态（已触发/未触发）。"""
    items = _load()
    if not items:
        return "当前没有定时提醒。"
    lines = []
    for i, it in enumerate(items, 1):
        mark = "🔔 已提醒" if it["triggered"] else "⏳ 待触发"
        lines.append(f"{i}. [{it['id']}] {it['time']}  {it['title']}  {mark}")
    return "提醒列表：\n" + "\n".join(lines)


@tool
def delete_reminder(reminder_id: str) -> str:
    """删除一条定时提醒。参数 reminder_id 是提醒的 id（来自 list_reminders 返回的 [id]）。"""
    items = _load()
    for it in items:
        if it["id"] == reminder_id:
            items.remove(it)
            _save(items)
            return f"已删除提醒：{it['title']}"
    return f"未找到 id={reminder_id} 的提醒。"


def _load_history() -> list[dict]:
    if _HISTORY.exists():
        try:
            return json.loads(_HISTORY.read_text(encoding="utf-8-sig"))  # 兼容 BOM
        except json.JSONDecodeError:
            return []
    return []


def _save_history(items: list[dict]) -> None:
    _HISTORY.parent.mkdir(exist_ok=True)
    _HISTORY.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@tool
def list_reminder_history(limit: int = 20) -> str:
    """查询提醒记录：所有已经触发过（到点提醒过用户）的提醒历史，按触发时间倒序。

    用户问"我之前设过哪些提醒/提醒记录/都提醒过我什么"时调用。
    limit 是返回的最大条数，默认 20。
    """
    items = _load_history()
    if not items:
        return "还没有提醒记录。"
    items = sorted(items, key=lambda x: x.get("triggered_at", ""), reverse=True)[:limit]
    lines = [f"{i}. {it['triggered_at']}  ⏰ {it['title']}" for i, it in enumerate(items, 1)]
    return "提醒记录（最近在前）：\n" + "\n".join(lines)


def check_due() -> list[dict]:
    """返回当前已到期且未触发的提醒（并将其标记为已触发、写入提醒记录）。供调度循环调用。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items = _load()
    due = [it for it in items if not it["triggered"] and it["time"] <= now]
    if due:
        for it in items:
            if it["id"] in {d["id"] for d in due}:
                it["triggered"] = True
        _save(items)
        # 同步写入提醒记录
        history = _load_history()
        for d in due:
            history.append({
                "id": d["id"],
                "title": d["title"],
                "time": d["time"],            # 预定的提醒时间
                "triggered_at": now,           # 实际触发时间
            })
        _save_history(history)
    return due
