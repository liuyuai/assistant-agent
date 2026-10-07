# -*- coding: utf-8 -*-
"""FastAPI 服务：网页 + SSE 流式聊天。

流式原理：LangGraph astream_events 产出两类事件——
- on_chat_model_stream：大模型逐 token 输出 → SSE `token` 事件
- on_tool_start / on_tool_end：工具调用生命周期 → SSE `tool` 事件
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .agent.graph import build_graph
from .rag import vector_store
from .tools import reminder

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

_graph = None
_reminder_clients: list[asyncio.Queue] = []
_loop_task: asyncio.Task | None = None


async def _reminder_loop() -> None:
    """后台调度循环：每秒检查到期提醒，触发后广播给前端 SSE 连接。"""
    while True:
        try:
            due = reminder.check_due()
            for r in due:
                payload = json.dumps(
                    {"type": "reminder", "title": r["title"], "time": r["time"]},
                    ensure_ascii=False,
                )
                for q in _reminder_clients[:]:
                    await q.put(payload)
        except Exception:  # noqa: BLE001 - 调度失败不影响服务
            pass
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时初始化：Checkpointer（会话持久化）+ 向量库入库 + 提醒调度循环。"""
    global _graph, _loop_task
    conn = await aiosqlite.connect(str(ROOT / "data" / "agent.db"))
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    _graph = build_graph(saver)
    vector_store.ingest()
    _loop_task = asyncio.create_task(_reminder_loop())
    yield
    if _loop_task:
        _loop_task.cancel()
    await conn.close()


app = FastAPI(title="个人助手 Agent", lifespan=lifespan)


def get_graph():
    return _graph


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/session/{thread_id}/history")
def history(thread_id: str) -> dict:
    """读取某会话的历史消息（用于刷新页面恢复对话），附带 token 统计。"""
    try:
        snapshot = get_graph().get_state({"configurable": {"thread_id": thread_id}})
        values = snapshot.values if snapshot else {}
        msgs = values.get("messages", []) if values else []
        out = []
        for m in msgs:
            if m.type == "human":
                out.append({"role": "user", "content": m.content})
            elif m.type == "ai":
                # 只返回最终回答（跳过带 tool_calls 的中间 AI 消息）
                if not getattr(m, "tool_calls", None):
                    out.append({"role": "assistant", "content": m.content})
        return {
            "ok": True,
            "messages": out,
            "summary": (values or {}).get("summary", ""),
            "token_stats": (values or {}).get("token_stats") or {"input": 0, "output": 0},
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "messages": [], "summary": "", "token_stats": {"input": 0, "output": 0}}


@app.get("/api/events")
async def events() -> StreamingResponse:
    """全局事件流（EventSource）：定时提醒到点主动推给前端。"""
    q: asyncio.Queue = asyncio.Queue()
    _reminder_clients.append(q)

    async def gen():
        try:
            yield "event: open\ndata: {}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # 心跳，防止连接被断开
        finally:
            try:
                _reminder_clients.remove(q)
            except ValueError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/tools")
async def tools() -> dict:
    """返回全部工具（中文名 + 分组 + 示例），供前端左侧栏渲染。"""
    from .tools import TOOLS, TOOL_DISPLAY, TOOL_EXAMPLES, TOOL_GROUPS

    desc = lambda t: (t.description or "").split("\n")[0].strip()[:60]
    by_name = {t.name: t for t in TOOLS}
    groups = []
    for gname, names in TOOL_GROUPS:
        groups.append({
            "group": gname,
            "tools": [
                {
                    "name": n,
                    "display": TOOL_DISPLAY.get(n, n),
                    "description": desc(by_name[n]) if n in by_name else "",
                    "example": TOOL_EXAMPLES.get(n, ""),
                }
                for n in names if n in by_name
            ],
        })
    return {"ok": True, "groups": groups}


@app.get("/api/reminders/history")
async def reminder_history(limit: int = 20) -> dict:
    """提醒记录：已触发的提醒，倒序返回。"""
    from .tools.reminder import _load_history

    items = _load_history()
    items = sorted(items, key=lambda x: x.get("triggered_at", ""), reverse=True)[:limit]
    return {"ok": True, "items": items}


@app.post("/api/chat")
async def chat(thread_id: str, message: str) -> StreamingResponse:
    async def event_stream():
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        input_state = {"messages": [HumanMessage(content=message, id=str(uuid.uuid4()))]}
        try:
            async for event in graph.astream_events(
                input_state, config=config, version="v2"
            ):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "") if chunk else ""
                    if content:
                        yield _sse("token", {"content": content})
                elif kind == "on_tool_start":
                    data = event.get("data", {})
                    yield _sse("tool", {"type": "start", "name": event.get("name", ""), "input": data.get("input")})
                elif kind == "on_tool_end":
                    data = event.get("data", {})
                    output = str(data.get("output", ""))[:500]
                    yield _sse("tool", {"type": "end", "name": event.get("name", ""), "output": output})
            # 流结束：读取最新 token 统计并推送给前端
            try:
                snap = await graph.aget_state(config)
                ts = (snap.values or {}).get("token_stats") or {"input": 0, "output": 0}
                yield _sse("stats", ts)
            except Exception:  # noqa: BLE001
                pass
            yield _sse("done", {})
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
