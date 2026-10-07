# -*- coding: utf-8 -*-
"""LangGraph 图编排：Agent 节点 + 工具节点 + 条件路由 + Checkpointer 记忆。

对比自研 for 循环版：LangGraph 把"循环、状态累积、历史持久化"抽象成图，
我们只声明节点和边，框架负责执行与记忆。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..llm import build_llm
from ..tools import TOOL_MAP
from ..tools.router import select_tools
from .prompt import SYSTEM_PROMPT


class AgentState(TypedDict):
    """图状态：messages 是全部对话消息（add_messages 自动追加合并）。

    summary     —— 历史摘要（超长对话时压缩旧消息，控制 token）
    token_stats —— 本次会话累计 token 用量（输入/输出），用于成本面板
    """
    messages: Annotated[list, add_messages]
    summary: str
    token_stats: dict


# 消息数超过该阈值时触发摘要压缩（保留最近 _KEEP_RECENT 条）
_SUMMARY_THRESHOLD = 16
_KEEP_RECENT = 8

# 触发 Query Rewrite 的指代词（新消息含这些词时先改写再进主模型）
_REFER_WORDS = ["它", "他", "她", "这", "那", "刚才", "上面", "之前", "那个", "这个", "那边"]

_QUERY_REWRITE_PROMPT = (
    "你是查询改写助手。把用户最新问题改写成一个独立完整的问题，"
    "消除代词和指代（如'它''这个''刚才说的'），补全缺失信息，只输出改写后的问题本身，不要任何解释。\n"
    "最近对话：\n{history}\n\n最新问题：{query}"
)

_SUMMARY_PROMPT = (
    "把以下对话历史压缩成一段简洁中文摘要，保留关键信息："
    "已安排的任务、时间节点、用户偏好、结论。直接输出摘要，不要其他内容。\n\n{content}"
)


def _count_tokens(state: AgentState, response: AIMessage) -> dict:
    """累计本次调用的 token 用量（usage_metadata 由 OpenAI 兼容 API 返回）。"""
    old = state.get("token_stats") or {"input": 0, "output": 0}
    meta = getattr(response, "usage_metadata", None) or {}
    return {
        "input": old.get("input", 0) + int(meta.get("input_tokens", 0)),
        "output": old.get("output", 0) + int(meta.get("output_tokens", 0)),
    }


def _maybe_summarize(state: AgentState) -> tuple[str, list] | None:
    """消息超阈值时，把旧消息压缩成摘要（返回新摘要 + 待删除消息 id 列表）。"""
    msgs = state["messages"]
    if len(msgs) < _SUMMARY_THRESHOLD:
        return None
    to_summarize = msgs[: -_KEEP_RECENT]  # 除最近 KEEP_RECENT 条外都总结
    if not to_summarize:
        return None
    old_summary = state.get("summary") or ""
    content = f"已有摘要：{old_summary}\n\n新增对话：\n" + "\n".join(
        f"{type(m).__name__}: {str(m.content)[:500]}" for m in to_summarize
    )
    resp = build_llm().invoke([SystemMessage(content=_SUMMARY_PROMPT.format(content=content))])
    new_summary = str(resp.content).strip()
    return new_summary, [m.id for m in to_summarize if getattr(m, "id", None)]


def _rewrite_query(state: AgentState, query: str) -> str:
    """Query Rewrite：新消息含指代词且有多轮历史时，改写为自包含问题。"""
    msgs = state["messages"]
    if len(msgs) < 3 or not any(w in query for w in _REFER_WORDS):
        return query
    history = "\n".join(
        f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {str(m.content)[:200]}"
        for m in msgs[-4:-1]
        if getattr(m, "content", None)
    )
    resp = build_llm().invoke([
        SystemMessage(content=_QUERY_REWRITE_PROMPT.format(history=history, query=query))
    ])
    rewritten = str(resp.content).strip().strip('"')
    return rewritten if rewritten else query


def _agent_node(state: AgentState) -> dict:
    """Agent 节点：把消息交给大模型（已绑定工具），模型决定是回答还是调用工具。

    - System Prompt 只在推理时临时拼接（不进持久化 state，避免重复累积）
    - 工具按意图路由动态绑定子集（工具越少模型选得越准）
    - 超长对话先压缩旧历史为摘要（省 token）
    - 新消息含指代词时先 Query Rewrite 再进主模型
    """
    updates: dict = {}

    # 1) 摘要压缩：超阈值时截断旧消息（RemoveMessage 删除 + 摘要消息占位）
    summarized = _maybe_summarize(state)
    if summarized:
        new_summary, del_ids = summarized
        updates["summary"] = new_summary
        updates["messages"] = [
            SystemMessage(id=str(uuid.uuid4()), content=f"（对话历史摘要：{new_summary}）"),
            *[RemoveMessage(id=i) for i in del_ids],
        ]

    # 2) 构造本轮输入消息（最新的用户消息做 Query Rewrite）
    msgs = state["messages"]
    if msgs and isinstance(msgs[-1], HumanMessage):
        rewritten = _rewrite_query(state, str(msgs[-1].content))
        if rewritten != msgs[-1].content:
            input_msgs = msgs[:-1] + [HumanMessage(content=rewritten)]
        else:
            input_msgs = msgs
    else:
        input_msgs = msgs

    # 3) 意图路由绑定工具子集 + 调主模型
    last_user = next(
        (m.content for m in reversed(input_msgs) if isinstance(m, HumanMessage)),
        "",
    )
    tools = select_tools(last_user)
    llm = build_llm().bind_tools(tools)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + input_msgs)

    updates["messages"] = [*(updates.get("messages") or []), response]
    updates["token_stats"] = _count_tokens(state, response)
    return updates


async def _tools_node(state: AgentState) -> dict:
    """工具节点：并行执行模型请求的所有工具（IO 密集用 asyncio.gather）。

    对比串行 for 循环：多个工具调用同时发出，总耗时取决于最慢的一个。
    """
    last = state["messages"][-1]
    tool_calls = last.tool_calls if isinstance(last, AIMessage) else []
    if not tool_calls:
        return {"messages": []}

    async def _run_one(call: dict) -> ToolMessage:
        name, args = call["name"], call.get("args") or {}
        try:
            # 工具是同步函数，用 asyncio.to_thread 丢线程池，避免阻塞事件循环
            result = await asyncio.to_thread(TOOL_MAP[name].invoke, args)
        except Exception as e:  # noqa: BLE001
            result = f"工具执行失败：{e}"
        return ToolMessage(content=str(result), tool_call_id=call["id"])

    msgs = await asyncio.gather(*(_run_one(c) for c in tool_calls))
    return {"messages": list(msgs)}


def _router(state: AgentState) -> str:
    """条件路由：模型要调工具 → 去 tools 节点；否则结束。"""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_graph(checkpointer):
    """构建并编译 LangGraph。checkpointer 由服务端注入（AsyncSqliteSaver 持久化会话）。"""
    graph = StateGraph(AgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _router, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)
