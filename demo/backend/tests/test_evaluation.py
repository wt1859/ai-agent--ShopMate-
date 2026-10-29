from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import ssl
import sys
from unittest.mock import Mock

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from demo_service import evaluation as evaluation_module
from demo_service.database import Repository
from demo_service.evaluation import evaluate


def test_default_evaluation_suite_is_offline_and_checks_human_review(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "should-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-used")

    remote_post = Mock(name="httpx.post")
    monkeypatch.setattr(httpx, "post", remote_post)
    report = evaluate()
    remote_post.assert_not_called()

    assert report["provider_mode"] == "offline_demo"
    assert report["total_cases"] == 8
    assert report["passed_cases"] == report["total_cases"]
    assert report["pass_rate"] == 1.0
    assert {name: counts["total"] for name, counts in report["dimensions"].items()} == {
        "intent": 9,
        "response": 8,
        "retrieval": 5,
        "route": 9,
        "safety": 8,
        "trace": 6,
    }
    assert report["dimensions"]["intent"]["passed"] > 0
    assert report["dimensions"]["safety"]["passed"] > 0
    cancel_case = next(case for case in report["cases"] if case["id"] == "cancel_requires_confirmation")
    assert cancel_case["passed"] is True
    assert cancel_case["checks"]
    assert all(check["passed"] for check in cancel_case["checks"])


def test_evaluation_checks_order_number_in_assistant_response(tmp_path):
    case_file = tmp_path / "wrong-order.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "wrong-order",
                "version": 1,
                "cases": [
                    {
                        "id": "response-order-number-mismatch",
                        "messages": [
                            {
                                "input": "查询订单 DEMO20261017001 的物流",
                                "expect": {
                                    "route": "orders",
                                    "order_no": "DEMO20261017002",
                                    "order_status": "paid",
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate(case_file)

    assert report["passed_cases"] == 0
    assert any("order_no: expected 'DEMO20261017002'" in failure for failure in report["cases"][0]["failures"])


def test_evaluation_reports_each_failed_assertion(tmp_path):
    case_file = tmp_path / "cases.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "deliberately-failing",
                "version": 1,
                "cases": [
                    {
                        "id": "wrong-route",
                        "messages": [
                            {
                                "input": "查询订单 DEMO20261017001 的物流",
                                "expect": {"intent_in": ["complaint"], "route": "human"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = evaluate(case_file)

    assert report["total_cases"] == 1
    assert report["passed_cases"] == 0
    assert report["pass_rate"] == 0.0
    assert report["dimensions"]["intent"] == {"passed": 0, "total": 1}
    assert report["dimensions"]["route"] == {"passed": 0, "total": 1}
    assert report["cases"][0]["failures"] == [
        "message[0].intent: expected one of ['complaint'], got 'order_query'",
        "message[0].route: expected 'human', got 'orders'",
    ]


def test_evaluation_rejects_boolean_suite_version(tmp_path):
    case_file = tmp_path / "boolean-version.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "boolean-version",
                "version": True,
                "cases": [
                    {
                        "id": "valid-case",
                        "messages": [{"input": "hello", "expect": {"route": "knowledge"}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="positive integer version"):
        evaluate(case_file)



def test_evaluation_rejects_case_without_checkable_expectation(tmp_path):
    case_file = tmp_path / "vacuous.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "vacuous",
                "version": 1,
                "cases": [
                    {
                        "id": "no-assertion",
                        "messages": [{"input": "查询订单 DEMO20261017001", "expect": {"order_no": "DEMO20261017001"}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checkable expectation"):
        evaluate(case_file)


def test_evaluation_rejects_empty_required_steps(tmp_path):
    case_file = tmp_path / "empty-steps.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "empty-steps",
                "version": 1,
                "cases": [
                    {
                        "id": "empty-steps",
                        "messages": [{"input": "hello", "expect": {"required_steps": []}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="required_steps must be a non-empty list"):
        evaluate(case_file)


def test_evaluation_rejects_null_status_expectations(tmp_path):
    invalid_expectations = [
        {"action_status": None},
        {"order_no": "DEMO20261017002", "order_status": None},
        {
            "order_no": "DEMO20261017002",
            "action_status": "pending",
            "confirm_action": True,
            "confirmed_action_status": None,
            "confirmed_order_status": "cancel_requested",
        },
        {
            "order_no": "DEMO20261017002",
            "action_status": "pending",
            "confirm_action": True,
            "confirmed_action_status": "confirmed",
            "confirmed_order_status": None,
        },
    ]
    case_file = tmp_path / "null-status.json"
    for index, expectation in enumerate(invalid_expectations):
        case_file.write_text(
            json.dumps(
                {
                    "suite": "null-status",
                    "version": 1,
                    "cases": [
                        {
                            "id": f"null-status-{index}",
                            "messages": [{"input": "取消订单 DEMO20261017002", "expect": expectation}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="status"):
            evaluate(case_file)



def test_evaluation_rejects_action_target_order_mismatch(monkeypatch):
    original_handle_message = evaluation_module.DemoEngine.handle_message

    def handle_message_with_wrong_action_order(self, session_id, content):
        result = original_handle_message(self, session_id, content)
        if result["actions"]:
            result["actions"][0]["order_no"] = "DEMO20261017003"
        return result

    monkeypatch.setattr(evaluation_module.DemoEngine, "handle_message", handle_message_with_wrong_action_order)
    report = evaluate()
    cancel_case = next(case for case in report["cases"] if case["id"] == "cancel_requires_confirmation")

    assert cancel_case["passed"] is False
    assert any("order_no target" in failure for failure in cancel_case["failures"])



def test_evaluation_rejects_confirmed_order_mismatch(monkeypatch):
    original_confirm_action = Repository.confirm_action

    def confirm_action_with_wrong_order(self, action_id):
        action, order = original_confirm_action(self, action_id)
        if order:
            order["order_no"] = "DEMO20261017003"
        return action, order

    monkeypatch.setattr(Repository, "confirm_action", confirm_action_with_wrong_order)
    report = evaluate()
    cancel_case = next(case for case in report["cases"] if case["id"] == "cancel_requires_confirmation")

    assert cancel_case["passed"] is False
    assert any("confirmed_order" in failure for failure in cancel_case["failures"])



def test_evaluation_rejects_confirmed_action_id_mismatch(monkeypatch):
    original_confirm_action = Repository.confirm_action

    def confirm_action_with_wrong_id(self, action_id):
        action, order = original_confirm_action(self, action_id)
        if action:
            action["id"] = "unrelated-action-id"
        return action, order

    monkeypatch.setattr(Repository, "confirm_action", confirm_action_with_wrong_id)
    report = evaluate()
    cancel_case = next(case for case in report["cases"] if case["id"] == "cancel_requires_confirmation")

    assert cancel_case["passed"] is False
    assert any("confirmed_action identity" in failure for failure in cancel_case["failures"])



def test_evaluation_rejects_noop_confirmation_expectations(tmp_path):
    invalid_expectations = [
        {
            "order_no": "DEMO20261017002",
            "action_status": "confirmed",
            "order_status": "paid",
            "confirm_action": True,
            "confirmed_action_status": "confirmed",
            "confirmed_order_status": "cancel_requested",
        },
        {
            "order_no": "DEMO20261017002",
            "action_status": "pending",
            "order_status": "cancel_requested",
            "confirm_action": True,
            "confirmed_action_status": "confirmed",
            "confirmed_order_status": "cancel_requested",
        },
    ]
    case_file = tmp_path / "noop-confirmation.json"
    for index, expectation in enumerate(invalid_expectations):
        case_file.write_text(
            json.dumps(
                {
                    "suite": "noop-confirmation",
                    "version": 1,
                    "cases": [
                        {
                            "id": f"noop-confirmation-{index}",
                            "messages": [{"input": "取消订单 DEMO20261017002", "expect": expectation}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="confirmation"):
            evaluate(case_file)



def test_evaluation_rejects_preconfigured_remote_provider(monkeypatch):
    original_engine = evaluation_module.DemoEngine

    class RemoteConfiguredEngine(original_engine):
        def __init__(self, db_path=None):
            super().__init__(db_path)
            self.classifier.api_key = "offline-test-only"

    network_posts = []

    def fake_httpx_post(*args, **kwargs):
        network_posts.append(True)
        with socket.socket() as client:
            client.connect(("203.0.113.1", 443))

    def block_socket_connect(*args, **kwargs):
        raise OSError("network blocked by test tripwire")

    monkeypatch.setattr(evaluation_module, "DemoEngine", RemoteConfiguredEngine)
    monkeypatch.setattr(httpx, "post", fake_httpx_post)
    monkeypatch.setattr(socket.socket, "connect", block_socket_connect)

    with pytest.raises(RuntimeError, match="provider API keys"):
        evaluate()
    assert network_posts == []


def test_evaluation_blocks_unexpected_socket_activity(monkeypatch):
    original_engine = evaluation_module.DemoEngine

    class SocketAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            with socket.socket() as client:
                client.connect(("203.0.113.1", 443))
            return super().handle_message(session_id, content)

    def block_socket_connect(*args, **kwargs):
        raise OSError("network blocked by test tripwire")

    monkeypatch.setattr(evaluation_module, "DemoEngine", SocketAttemptEngine)
    monkeypatch.setattr(socket.socket, "connect", block_socket_connect)

    with pytest.raises(RuntimeError, match="offline evaluation blocked network access"):
        evaluate()



def test_evaluation_blocks_unexpected_dns_resolution(monkeypatch):
    original_engine = evaluation_module.DemoEngine

    class DnsAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            socket.gethostbyname("example.invalid")
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", DnsAttemptEngine)

    with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*gethostbyname"):
        evaluate()


def test_evaluation_blocks_socket_sendmsg_when_available(monkeypatch):
    if not hasattr(socket.socket, "sendmsg"):
        pytest.skip("socket.sendmsg is not available on this platform")

    original_engine = evaluation_module.DemoEngine

    class SendMessageAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                getattr(client, "sendmsg")([b"offline-eval-probe"], [], 0, ("203.0.113.1", 443))
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", SendMessageAttemptEngine)

    with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*sendmsg"):
        evaluate()



def test_evaluation_blocks_sendfile_on_preconnected_socket(monkeypatch, tmp_path):
    original_engine = evaluation_module.DemoEngine
    sender, receiver = socket.socketpair()
    sender.settimeout(0.1)
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"offline evaluation probe")

    class SendfileAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            with payload.open("rb") as file:
                sender.sendfile(file)
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", SendfileAttemptEngine)
    try:
        with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*sendfile"):
            evaluate()
    finally:
        sender.close()
        receiver.close()


def test_evaluation_blocks_ssl_write_on_preconnected_socket(monkeypatch):
    original_engine = evaluation_module.DemoEngine
    sender, receiver = socket.socketpair()
    sender.settimeout(0.1)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    tls_sender = context.wrap_socket(sender, server_hostname="localhost", do_handshake_on_connect=False)

    class SslWriteAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            tls_sender.write(b"offline evaluation probe")
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", SslWriteAttemptEngine)
    try:
        with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*write"):
            evaluate()
    finally:
        tls_sender.close()
        receiver.close()



def test_evaluation_blocks_ssl_handshake_on_preconnected_socket(monkeypatch):
    original_engine = evaluation_module.DemoEngine
    sender, receiver = socket.socketpair()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    tls_sender = context.wrap_socket(sender, server_hostname="localhost", do_handshake_on_connect=False)
    received = []

    def capture_peer_bytes():
        receiver.settimeout(0.1)
        try:
            received.append(receiver.recv(4096))
        except TimeoutError:
            pass

    class SslHandshakeAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            capture_peer_bytes()
            tls_sender.do_handshake()
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", SslHandshakeAttemptEngine)
    try:
        with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*do_handshake"):
            evaluate()
        capture_peer_bytes()
        assert received == []
    finally:
        tls_sender.close()
        receiver.close()



def test_evaluation_blocks_sslobject_handshake_before_emitting_tls_bytes(monkeypatch):
    original_engine = evaluation_module.DemoEngine
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    incoming = ssl.MemoryBIO()
    outgoing = ssl.MemoryBIO()
    tls_object = context.wrap_bio(incoming, outgoing, server_hostname="localhost")

    class SslObjectHandshakeAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            tls_object.do_handshake()
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", SslObjectHandshakeAttemptEngine)

    with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*do_handshake"):
        evaluate()
    assert outgoing.pending == 0



def test_evaluation_blocks_os_write_on_preconnected_socket(monkeypatch):
    if os.name == "nt":
        pytest.skip("os.write cannot target a Windows socket descriptor")
    original_engine = evaluation_module.DemoEngine
    sender, receiver = socket.socketpair()

    class OsWriteAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            os.write(sender.fileno(), b"offline evaluation probe")
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", OsWriteAttemptEngine)
    try:
        with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*os.write"):
            evaluate()
    finally:
        sender.close()
        receiver.close()


def test_evaluation_blocks_os_sendfile_on_preconnected_socket(monkeypatch, tmp_path):
    if not hasattr(os, "sendfile"):
        pytest.skip("os.sendfile is not available on this platform")

    original_engine = evaluation_module.DemoEngine
    sender, receiver = socket.socketpair()
    payload = tmp_path / "os-payload.bin"
    payload.write_bytes(b"offline evaluation probe")

    class OsSendfileAttemptEngine(original_engine):
        def handle_message(self, session_id, content):
            with payload.open("rb") as file:
                getattr(os, "sendfile")(sender.fileno(), file.fileno(), 0, payload.stat().st_size)
            return super().handle_message(session_id, content)

    monkeypatch.setattr(evaluation_module, "DemoEngine", OsSendfileAttemptEngine)
    try:
        with pytest.raises(RuntimeError, match="offline evaluation blocked network access.*os.sendfile"):
            evaluate()
    finally:
        sender.close()
        receiver.close()



def test_evaluation_rejects_duplicate_case_ids(tmp_path):
    case_file = tmp_path / "duplicate.json"
    case_file.write_text(
        json.dumps(
            {
                "suite": "duplicate",
                "version": 1,
                "cases": [
                    {"id": "same", "messages": [{"input": "hello", "expect": {"route": "knowledge"}}]},
                    {"id": "same", "messages": [{"input": "hello", "expect": {"route": "knowledge"}}]},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate case id"):
        evaluate(case_file)
