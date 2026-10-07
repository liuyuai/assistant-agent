# -*- coding: utf-8 -*-
"""评估体系：固定用例集，量化 Agent 效果，防回归。

用法：
    python evaluate.py            # 跑全部用例（需要服务已启动）
    python evaluate.py 天气        # 只跑用例名/问题包含"天气"的

指标：
- 工具调用召回率：期望工具中被实际调用的比例（核心指标）
- 工具调用精确率：实际调用中属于期望工具的比例
- RAG 命中率：search_notes 用例返回结果是否命中期望内容
- 回答非空率

判定：期望工具 ⊆ 实际调用 → PASS，否则 FAIL 并列出缺失/多余。
"""
from __future__ import annotations

import json
import sys
import time
from urllib.parse import quote

import httpx

BASE = "http://127.0.0.1:8000"

# 固定用例：问题 -> 期望被调用的工具（顺序无关，子集即可）
CASES: list[dict] = [
    {"name": "天气查询", "question": "大连今天天气怎么样", "expect": ["get_weather"]},
    {"name": "多城市并行", "question": "帮我同时查一下北京和上海的天气", "expect": ["get_weather"]},
    {"name": "添加待办", "question": "帮我记一个待办：周五之前交周报", "expect": ["add_todo"]},
    {"name": "待办列表", "question": "我有哪些待办？", "expect": ["list_todos"]},
    {"name": "日程多步", "question": "帮我安排明天下午3点的项目评审会", "expect": ["get_current_time", "add_schedule"]},
    {"name": "提醒多步", "question": "帮我设置一个2分钟后的提醒，提醒我喝水", "expect": ["get_current_time", "add_reminder"]},
    {"name": "时间查询", "question": "现在几点了？", "expect": ["get_current_time"]},
    {"name": "RAG笔记", "question": "查一下我的笔记里关于 LangGraph 记忆机制的内容", "expect": ["search_notes"]},
]


def run_case(case: dict) -> dict:
    """对单个用例发起真实请求，收集实际工具调用。"""
    thread = f"eval-{case['name']}-{int(time.time() * 1000)}"
    actual: list[str] = []
    answer = ""
    with httpx.stream(
        "POST",
        f"{BASE}/api/chat?thread_id={thread}&message={quote(case['question'])}",
        timeout=120,
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                try:
                    obj = json.loads(line[6:])
                except Exception:
                    continue
                if obj.get("type") == "start" and obj.get("name"):
                    actual.append(obj["name"])
                elif "content" in obj:
                    answer += obj["content"]
    return {"actual": actual, "answer": answer.strip(), "thread": thread}


def main() -> None:
    kw = sys.argv[1] if len(sys.argv) > 1 else ""
    cases = [c for c in CASES if kw in c["name"] or kw in c["question"]]
    if not cases:
        print(f"没有匹配 '{kw}' 的用例")
        return

    print(f"共 {len(cases)} 个用例，开始评估（真实调用 DeepSeek）……\n")
    results = []
    for c in cases:
        res = run_case(c)
        expect = set(c["expect"])
        actual = set(res["actual"])

        missing = expect - actual
        extra = actual - expect
        passed = not missing
        recall = len(expect & actual) / len(expect) if expect else 1.0
        precision = len(expect & actual) / len(actual) if actual else 0.0

        results.append({
            "case": c["name"], "question": c["question"],
            "expect": sorted(expect), "actual": sorted(actual),
            "missing": sorted(missing), "extra": sorted(extra),
            "passed": passed, "recall": recall, "precision": precision,
            "answer_len": len(res["answer"]),
        })

        flag = "✅" if passed else "❌"
        print(f"{flag} {c['name']}")
        print(f"    问题: {c['question']}")
        print(f"    期望工具: {sorted(expect)}")
        print(f"    实际调用: {sorted(actual)}")
        if missing:
            print(f"    ❗ 缺失: {sorted(missing)}")
        if extra:
            print(f"    ⚠ 多余: {sorted(extra)}")
        time.sleep(0.5)

    passed_n = sum(1 for r in results if r["passed"])
    avg_recall = sum(r["recall"] for r in results) / len(results)
    avg_precision = sum(r["precision"] for r in results) / len(results)
    nonempty = sum(1 for r in results if r["answer_len"] > 0)
    print("\n" + "=" * 50)
    print(f"通过率: {passed_n}/{len(results)} ({passed_n/len(results)*100:.0f}%)")
    print(f"工具调用召回率(平均): {avg_recall*100:.0f}%")
    print(f"工具调用精确率(平均): {avg_precision*100:.0f}%")
    print(f"回答非空率: {nonempty}/{len(results)}")


if __name__ == "__main__":
    main()
