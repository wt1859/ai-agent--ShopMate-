from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from demo_service.engine import DemoEngine

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

app = FastAPI(title="电商客服 Agent Demo", version="0.1.0", docs_url="/api/docs", redoc_url=None)
engine = DemoEngine()


@app.middleware("http")
async def route_demo_api_prefix(request, call_next):
    """Expose every demo API under one stable same-origin prefix."""
    prefix = "/api/demo"
    path = request.scope["path"]
    if path == prefix:
        request.scope["path"] = "/"
    elif path.startswith(prefix + "/"):
        request.scope["path"] = path[len(prefix):]
        request.scope["raw_path"] = request.scope["path"].encode("utf-8")
    return await call_next(request)


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
ASSET_DIR = FRONTEND_DIST / "assets"
if ASSET_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=2000)


class KnowledgeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=10, max_length=12000)
    category: str = Field(min_length=1, max_length=40)
    source: str = Field(default="管理员新增", max_length=80)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    domains: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=10)


@app.get("/status")
def get_status() -> dict[str, Any]:
    return engine.status()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "demo"}


@app.get("/sessions")
def get_sessions() -> dict[str, Any]:
    return {"sessions": engine.list_sessions()}


@app.post("/sessions")
def create_session() -> dict[str, Any]:
    session = engine.create_session()
    welcome = "您好，我是客服 Agent 演示助手。可以试试查询演示订单、商品库存、售后政策，或测试投诉转人工流程。"
    engine.repository.add_message(session["id"], "assistant", welcome)
    return {"session": session, "welcome_message": welcome, "quick_replies": ["查询订单 DEMO20261017001", "七天无理由退货吗？", "SKU-PHONE-001 有库存吗？"]}


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> dict[str, Any]:
    if not engine.repository.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"messages": engine.messages(session_id)}


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    if not engine.repository.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"deleted": True}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        return await run_in_threadpool(engine.handle_message, request.session_id, request.content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/actions/{action_id}/confirm")
def confirm_action(action_id: str) -> dict[str, Any]:
    action, order = engine.repository.confirm_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="演示操作不存在")
    return {
        "message": "已提交演示申请；没有连接真实订单或支付系统。",
        "action": action,
        "order": order,
    }


@app.get("/knowledge")
def get_knowledge(category: str | None = None) -> dict[str, Any]:
    documents = engine.list_knowledge(category)
    return {"documents": documents, "categories": sorted({item["category"] for item in engine.list_knowledge()})}


@app.post("/knowledge")
def add_knowledge(request: KnowledgeRequest) -> dict[str, Any]:
    item = engine.repository.add_knowledge(request.title.strip(), request.content.strip(), request.category.strip(), request.source.strip())
    return {"document": item, "count": len(engine.list_knowledge())}


@app.delete("/knowledge/{document_id}")
def delete_knowledge(document_id: str) -> dict[str, bool]:
    if not engine.repository.delete_knowledge(document_id):
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"deleted": True}


@app.post("/search")
def search(request: SearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    results = engine.search(request.query, request.domains, request.top_k)
    return {
        "results": results,
        "strategy": "BM25 + dense + RRF + rerank",
        "embedding_provider": engine.embedding_provider,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@app.get("/orders")
def get_orders() -> dict[str, Any]:
    return {"orders": engine.list_orders()}


@app.get("/products")
def get_products() -> dict[str, Any]:
    return {"products": engine.list_products()}


@app.get("/traces")
def get_traces() -> dict[str, Any]:
    return {"traces": engine.repository.list_traces()}


@app.get("/metrics")
def get_metrics() -> dict[str, int]:
    return engine.repository.metrics()


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> Any:
    """Serve the built SPA; keep API paths explicit and same-origin."""
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API 路径不存在")
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
    return JSONResponse(
        {"message": "后端已运行。先在 demo/frontend 执行 npm install && npm run build，然后刷新此页面。", "api_docs": "/api/docs"},
        status_code=200,
    )
