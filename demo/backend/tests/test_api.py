from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
import app as demo_app


def client_for_test(tmp_path):
    demo_app.engine = demo_app.DemoEngine(str(tmp_path / "api-test.sqlite3"))
    return TestClient(demo_app.app)


def test_demo_api_is_available_under_namespaced_prefix(tmp_path):
    client = client_for_test(tmp_path)
    response = client.get("/api/demo/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"


def test_status_exposes_local_demo_providers_and_seed_counts(tmp_path):
    client = client_for_test(tmp_path)
    result = client.get("/status")
    assert result.status_code == 200
    body = result.json()
    assert body["mode"] == "demo"
    assert body["intent_provider"] == "local_rules"
    assert body["orders"] == 3
    assert body["documents"] >= 5


def test_chat_to_order_lookup_returns_trace_and_demo_citation(tmp_path):
    client = client_for_test(tmp_path)
    session = client.post("/sessions").json()["session"]
    result = client.post("/chat", json={"session_id": session["id"], "content": "查询订单 DEMO20261017001 的物流"})
    assert result.status_code == 200
    body = result.json()
    assert body["decision"]["intent"] in {"order_query", "logistics"}
    assert "已发货" in body["message"]["content"]
    assert body["trace"]["route"] == "orders"
    assert body["trace"]["steps"]
    assert body["citations"]


def test_confirm_demo_cancel_is_explicit_and_does_not_claim_real_execution(tmp_path):
    client = client_for_test(tmp_path)
    session = client.post("/sessions").json()["session"]
    response = client.post("/chat", json={"session_id": session["id"], "content": "取消订单 DEMO20261017002"})
    assert response.status_code == 200
    action = response.json()["actions"][0]
    assert action["status"] == "pending"
    assert "不会直接执行" in response.json()["message"]["content"]
    confirmed = client.post(f"/actions/{action['id']}/confirm", json={}).json()
    assert "没有连接真实订单" in confirmed["message"]
    assert confirmed["action"]["status"] == "confirmed"
    assert confirmed["order"]["status"] == "cancel_requested"
    history = client.get(f"/sessions/{session['id']}/messages").json()["messages"]
    latest_action = [message for message in history if message.get("actions")][-1]["actions"][0]
    assert latest_action["status"] == "confirmed"


def test_knowledge_add_search_delete_persists_in_demo_db(tmp_path):
    client = client_for_test(tmp_path)
    document = client.post("/knowledge", json={"title": "检测知识条目", "content": "此条目用于测试关键词退换规则与混合检索。", "category": "after_sales"}).json()["document"]
    results = client.post("/search", json={"query": "退换规则", "domains": ["after_sales"]}).json()["results"]
    assert any(item["id"] == document["id"] for item in results)
    assert client.delete(f"/knowledge/{document['id']}").json()["deleted"] is True


def test_reject_unknown_session_and_malformed_chat(tmp_path):
    client = client_for_test(tmp_path)
    missing = client.post("/chat", json={"session_id": "missing", "content": "你好"})
    assert missing.status_code == 404
    malformed = client.post("/chat", json={"session_id": "x", "content": ""})
    assert malformed.status_code == 422
