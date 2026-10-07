# 个人助手 Agent（LangChain + LangGraph）

一个对话式个人助手：管理待办/日程、查天气/时间、基于个人笔记 RAG 问答。
**非生产演示项目**，用于展示 LangChain + LangGraph 的 Agent 开发能力。

## 技术栈

| 层 | 技术 |
|---|---|
| 模型 | DeepSeek（deepseek-chat，OpenAI 兼容协议，经 ChatOpenAI 接入） |
| Agent 编排 | **LangGraph** StateGraph：agent 节点 + tools 节点 + 条件路由 + Checkpointer 记忆 |
| 工具 | LangChain `@tool` 声明式工具（14 个），`bind_tools` 做 Function Calling |
| RAG | Chroma 向量库 + 本地 ONNX embedding（all-MiniLM-L6-v2，无需 API key） |
| 记忆 | LangGraph Checkpointer（**AsyncSqliteSaver**，按 thread_id 持久化，重启不丢历史） |
| 服务 | FastAPI + SSE 流式输出（astream_events：token 事件 + 工具事件） |
| 前端 | 原生 HTML/JS：对话区 + 分组折叠侧栏 + Token 面板 + 语音输入 |

## 功能

- ✅ 待办管理：添加/列出/完成（`add_todo` / `list_todos` / `complete_todo`）
- ✅ 日程管理：添加/列出/删除，时间口语换算（"明天下午3点" → 先查当前时间再换算）
- ✅ **定时提醒**：`add_reminder` / `list_reminders` / `delete_reminder` + 后台调度循环 + SSE 主动推送 + 页面 Toast
- ✅ **提醒记录**：触发过的提醒自动存档（`reminder_history.json`），`list_reminder_history` 随时可查
- ✅ 天气查询：真实数据（wttr.in 免费接口），失败降级模拟
- ✅ 时间查询：`get_current_time`
- ✅ 个人笔记 RAG：`search_notes` 检索 + `add_note` 保存新笔记
- ✅ 多轮记忆：同一会话上下文累积（LangGraph Checkpointer）
- ✅ 流式输出 + 工具调用可视化（SSE + astream_events）
- ✅ **意图路由**：按问题域只绑定子集工具（`router.py`），降低模型工具选择错误率，未命中兜底全量
- ✅ **多工具并行执行**：工具节点 `asyncio.gather` 并行（"同时查两个城市天气"一次发出）
- ✅ **长对话摘要压缩**：消息超阈值自动用 LLM 总结旧历史（RemoveMessage 截断），控制 token 成本
- ✅ **Query Rewrite**：新消息含代词时自动改写为自包含问题（"那上海呢？"→ 带上下文）
- ✅ **Token 成本统计**：会话级 token 累计 + 前端成本面板（按 DeepSeek 单价估算）
- ✅ **语音输入**：浏览器原生 Web Speech API（Chrome），说话即输入
- ✅ **评估体系**：`python evaluate.py` 固定用例集，量化工具调用准确率/召回率（防回归）

## 目录结构

```
assistant-agent/
├── run.py                    # 启动入口：python run.py
├── evaluate.py               # 评估体系：python evaluate.py（需服务已启动）
├── .env                      # LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / TEMPERATURE
├── app/
│   ├── config.py             # 配置读取
│   ├── llm.py                # ChatOpenAI → DeepSeek
│   ├── server.py             # FastAPI + SSE（astream_events 流式）
│   ├── tools/                # 14 个工具（@tool 声明式）+ 意图路由
│   │   ├── todo.py / schedule.py / weather.py / time_tool.py / notes.py / reminder.py
│   │   └── router.py         # 意图路由：按域动态绑定工具子集
│   ├── rag/vector_store.py   # Chroma 入库 + 检索（Markdown 标题分块）
│   └── agent/
│       ├── prompt.py         # System Prompt
│       └── graph.py          # LangGraph StateGraph（核心）
├── static/index.html         # 聊天界面（含 EventSource 提醒 Toast）
├── data/
│   ├── notes/*.md            # 个人笔记（RAG 数据源）
│   ├── todos.json / schedules.json / reminders.json
│   ├── chroma_db/            # 向量库
│   └── agent.db              # 会话历史（SQLite）
```

## 核心代码：LangGraph 图编排

```python
# app/agent/graph.py
graph = StateGraph(AgentState)              # 状态：messages（add_messages 自动追加）
graph.add_node("agent", _agent_node)        # 大模型决策（绑定工具）
graph.add_node("tools", _tools_node)        # 执行模型请求的工具
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", _router,   # 有 tool_calls → tools；否则结束
                            {"tools": "tools", END: END})
graph.add_edge("tools", "agent")            # 工具结果回到大模型（核心循环）
return graph.compile(checkpointer=saver)    # Checkpointer 持久化会话
```

## 流式输出（SSE）

```python
async for event in graph.astream_events(input_state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":   # 大模型逐 token
        yield token
    elif event["event"] == "on_tool_start/end":     # 工具调用生命周期
        yield tool_event
```

## 运行

```bash
pip install -r requirements.txt   # 或直接复用已装环境
python run.py                     # http://127.0.0.1:8000
```

## 定时提醒（主动推送）

```python
# app/server.py —— 后台调度循环
async def _reminder_loop():
    while True:
        due = reminder.check_due()              # 到期且未触发的提醒
        for r in due:
            await broadcast({"type": "reminder", "title": r["title"], ...})
        await asyncio.sleep(1)

# GET /api/events —— SSE 全局事件流
# 前端 EventSource("/api/events") 收到 reminder 事件 → 弹 Toast
```

- 对话设置："帮我设置一个明天早上9点的提醒，提醒我带电脑" → LLM 先查当前时间换算 → `add_reminder`
- 到点触发：后台循环检测到期 → 广播到所有 SSE 连接 → 页面右上角弹 Toast（20 秒后自动消失）
- 触发存档：到期提醒自动写入 `data/reminder_history.json`（含预定时间 + 实际触发时间）
- 记录查询："我之前设置过哪些提醒？" → `list_reminder_history` → 倒序返回最近 20 条
- 非生产取舍：asyncio 轮询 + JSON 文件；生产可换 APScheduler/Celery + Redis，推送换 WebSocket

## 演示话术

- "大连今天天气怎么样？" → get_weather（真实数据）
- "帮我记一个待办：周五之前交周报" → add_todo
- "帮我安排明天下午3点的项目评审会" → get_current_time + add_schedule（多步推理）
- "帮我同时查一下北京和上海的天气" → 两个 get_weather 并行执行
- "那上海呢？"（前面聊过大连）→ Query Rewrite 消解代词 → 查上海
- "查一下我的笔记里关于 LangGraph 的记忆机制" → search_notes（RAG）
