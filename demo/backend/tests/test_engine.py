from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from demo_service.engine import DemoEngine


@pytest.fixture
def engine(tmp_path):
    return DemoEngine(str(tmp_path / "engine.sqlite3"))


def test_hybrid_search_returns_keyword_and_semantic_candidates(engine):
    hits = engine.search("商品不合适想退货", domains=["after_sales"], top_k=5)
    assert hits
    assert any(hit["category"] == "after_sales" for hit in hits)
    assert {"dense_score", "bm25_score", "score"} <= set(hits[0])
    assert engine.embedding_provider == "local_char_tfidf_demo"


def test_intent_route_sends_live_order_questions_to_order_tool(engine):
    decision = engine.classify("订单 DEMO20261017001 到哪里了？")
    assert decision["intent"] in {"order_query", "logistics"}
    assert "orders" in decision["domains"]
    assert decision["provider"] == "local_rules"


def test_refund_request_does_not_claim_to_execute_refund(engine):
    session = engine.create_session()
    result = engine.handle_message(session["id"], "我想取消订单 DEMO20261017002")
    assert result["actions"]
    assert result["actions"][0]["status"] == "pending"
    assert "确认" in result["message"]["content"]


def test_follow_up_refund_question_uses_session_context(engine):
    session = engine.create_session()
    engine.handle_message(session["id"], "商品不合适，可以退吗？")
    result = engine.handle_message(session["id"], "那订单已经发货了呢？")
    assert result["decision"]["intent"] in {"refund_return", "order_query", "logistics"}
    assert result["trace"]["steps"]


def test_seed_records_and_trace_are_available(engine):
    assert any(row["order_no"] == "DEMO20261017001" for row in engine.list_orders())
    assert any(row["sku"] == "SKU-PHONE-001" for row in engine.list_products())
    result = engine.handle_message(engine.create_session()["id"], "七天无理由退货吗？")
    assert result["trace"]["route"] in {"knowledge", "knowledge+orders", "human", "product"}
    assert result["trace"]["steps"]
    assert result["citations"]
