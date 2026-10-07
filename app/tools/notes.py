# -*- coding: utf-8 -*-
"""个人笔记 RAG 工具：搜索笔记 + 新增笔记。"""
from __future__ import annotations

from langchain_core.tools import tool

from ..rag import vector_store


@tool
def search_notes(query: str) -> str:
    """从个人知识库检索笔记。参数 query 是自然语言问题，例如"我记录过 LangGraph 的什么要点"。

    当用户问的是个人笔记/资料/回忆性内容时使用；回答时基于检索结果，不要编造。
    """
    hits = vector_store.search(query, k=3)
    if not hits:
        return "个人笔记中没有检索到相关内容。"
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[{i}]（来自 {h['source']}，相关度 {h['score']}）\n{h['text']}")
    return "\n\n".join(parts)


@tool
def add_note(title: str, content: str) -> str:
    """把一段内容保存为个人笔记（markdown 文件），之后可被检索。

    参数 title 是笔记标题，content 是笔记正文。
    """
    path = vector_store.add_note_file(title, content)
    return f"笔记已保存：{path.name}（已入库可检索）"
