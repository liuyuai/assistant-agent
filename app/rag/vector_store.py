# -*- coding: utf-8 -*-
"""个人笔记向量库：Chroma + 本地 ONNX embedding（无需 API key）。

- 入库：读 data/notes/*.md → 按 Markdown 标题结构化分块 → upsert 到 Chroma
- 检索：query 向量化 → 余弦相似度 top_k
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

ROOT = Path(__file__).resolve().parents[2]
NOTES_DIR = ROOT / "data" / "notes"
CHROMA_DIR = ROOT / "data" / "chroma_db"
COLLECTION = "personal_notes"

_embed_fn = embedding_functions.DefaultEmbeddingFunction()
_client = chromadb.PersistentClient(path=str(CHROMA_DIR))


def _collection():
    return _client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
        embedding_function=_embed_fn,
    )


def chunk_markdown(text: str, source: str) -> list[dict]:
    """按 Markdown 标题分块：每个 '## 小节' 为一块，块头带上文章标题，保证上下文完整。"""
    lines = text.splitlines()
    title = ""
    chunks: list[dict] = []
    cur_title = ""
    cur_lines: list[str] = []

    def flush() -> None:
        nonlocal cur_lines
        if cur_lines:
            body = "\n".join(cur_lines).strip()
            if body:
                header = f"# {title}\n" if title else ""
                if cur_title and cur_title != title:
                    header += f"## {cur_title}\n"
                chunks.append({"text": header + body, "source": source})
            cur_lines = []

    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            flush()
            title = line[2:].strip()
            cur_title = ""
        elif line.startswith("## "):
            flush()
            cur_title = line[3:].strip()
        else:
            cur_lines.append(line)
    flush()
    return chunks or [{"text": text, "source": source}]


def ingest(verbose: bool = False) -> int:
    """全量重建向量库（非生产：删库重建，简单可靠）。"""
    try:
        _client.delete_collection(COLLECTION)
    except Exception:  # noqa: BLE001 - 集合不存在时忽略
        pass
    col = _collection()
    docs: list[dict] = []
    if not NOTES_DIR.exists():
        return 0
    for md in sorted(NOTES_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        docs.extend(chunk_markdown(text, source=md.name))
    if docs:
        ids = [hashlib.md5((d["source"] + d["text"]).encode()).hexdigest() for d in docs]
        col.upsert(
            ids=ids,
            documents=[d["text"] for d in docs],
            metadatas=[{"source": d["source"]} for d in docs],
        )
    if verbose:
        print(f"已入库 {len(docs)} 个分块")
    return len(docs)


def search(query: str, k: int = 3) -> list[dict]:
    """检索笔记，返回 [{text, source, score}]。"""
    col = _collection()
    r = col.query(query_texts=[query], n_results=k)
    out = []
    if r and r["documents"]:
        for i, doc in enumerate(r["documents"][0]):
            out.append({
                "text": doc,
                "source": (r["metadatas"][0][i] or {}).get("source", ""),
                "score": round(1 - (r["distances"][0][i] if r.get("distances") else 0), 4),
            })
    return out


def add_note_file(title: str, content: str) -> Path:
    """新增一篇笔记 md 并增量入库（返回文件路径）。"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    path = NOTES_DIR / f"{safe}.md"
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    col = _collection()
    chunks = chunk_markdown(path.read_text(encoding="utf-8"), source=path.name)
    if chunks:
        ids = [hashlib.md5((c["source"] + c["text"]).encode()).hexdigest() for c in chunks]
        col.upsert(
            ids=ids,
            documents=[c["text"] for c in chunks],
            metadatas=[{"source": c["source"]} for c in chunks],
        )
    return path
