# -*- coding: utf-8 -*-
"""待办管理工具（JSON 文件存储，非生产用简单持久化）。"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from langchain_core.tools import tool

_DATA = Path(__file__).resolve().parents[2] / "data" / "todos.json"


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
def add_todo(title: str) -> str:
    """添加一条待办事项。参数 title 是待办内容，例如"周三下午开周会"。"""
    items = _load()
    item = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "done": False,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(item)
    _save(items)
    return f"已添加待办：{title}（共 {len(items)} 条，未完成 {sum(1 for i in items if not i['done'])} 条）"


@tool
def list_todos() -> str:
    """列出所有待办事项，包含完成状态。"""
    items = _load()
    if not items:
        return "当前没有待办事项。"
    lines = []
    for i, it in enumerate(items, 1):
        mark = "✅" if it["done"] else "⬜"
        lines.append(f"{i}. {mark} [{it['id']}] {it['title']}")
    done_n = sum(1 for it in items if it["done"])
    return "待办列表：\n" + "\n".join(lines) + f"\n（共 {len(items)} 条，已完成 {done_n} 条）"


@tool
def complete_todo(todo_id: str) -> str:
    """把待办标记为已完成。参数 todo_id 是待办的 id（来自 list_todos 返回的 [id]）。"""
    items = _load()
    for it in items:
        if it["id"] == todo_id:
            it["done"] = True
            _save(items)
            return f"已完成：{it['title']}"
    return f"未找到 id={todo_id} 的待办，请先用 list_todos 查看。"
