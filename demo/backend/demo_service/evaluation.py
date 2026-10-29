from __future__ import annotations

import argparse
import json
import math
import os
import socket
import ssl
import sys
import tempfile
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch

from demo_service.engine import DemoEngine


DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "cases.json"
SUPPORTED_EXPECTATIONS = {
    "intent_in",
    "route",
    "contains",
    "citation_category",
    "action_status",
    "order_no",
    "order_status",
    "required_steps",
    "confirm_action",
    "confirmed_action_status",
    "confirmed_order_status",
}
STATUS_EXPECTATIONS = {
    "action_status": {"pending", "confirmed"},
    "order_status": {"pending", "paid", "shipped", "delivered", "cancel_requested", "refund_requested"},
    "confirmed_action_status": {"confirmed"},
    "confirmed_order_status": {"cancel_requested", "refund_requested"},
}
NETWORK_BOUNDARIES = (
    (os, "write"),
    (os, "writev"),
    (os, "sendfile"),
    (os, "splice"),
    (socket, "getaddrinfo"),
    (socket, "gethostbyname"),
    (socket, "gethostbyname_ex"),
    (socket, "gethostbyaddr"),
    (socket, "getnameinfo"),
    (socket, "create_connection"),
    (socket.socket, "connect"),
    (socket.socket, "connect_ex"),
    (socket.socket, "send"),
    (socket.socket, "sendall"),
    (socket.socket, "sendto"),
    (socket.socket, "sendmsg"),
    (socket.socket, "sendfile"),
    (ssl.SSLSocket, "connect"),
    (ssl.SSLSocket, "connect_ex"),
    (ssl.SSLSocket, "send"),
    (ssl.SSLSocket, "sendall"),
    (ssl.SSLSocket, "sendto"),
    (ssl.SSLSocket, "sendmsg"),
    (ssl.SSLSocket, "sendfile"),
    (ssl.SSLSocket, "write"),
    (ssl.SSLSocket, "do_handshake"),
    (ssl.SSLSocket, "unwrap"),
    (ssl.SSLSocket, "shutdown"),
    (ssl.SSLSocket, "verify_client_post_handshake"),
    (ssl.SSLObject, "write"),
    (ssl.SSLObject, "do_handshake"),
    (ssl.SSLObject, "unwrap"),
    (ssl.SSLObject, "shutdown"),
)


def _block_network(target: str, attempts: set[str]):
    def blocked(*args: Any, **kwargs: Any) -> None:
        attempts.add(target)
        raise RuntimeError(f"offline evaluation blocked network access ({target})")

    return blocked


def _network_boundaries() -> list[tuple[Any, str]]:
    return [(owner, name) for owner, name in NETWORK_BOUNDARIES if hasattr(owner, name)]


def _assert_local_providers(engine: DemoEngine) -> None:
    providers = (engine.classifier.provider, engine.embedding_provider, engine.responder.provider)
    keys = (engine.classifier.api_key, engine.retriever.api_key, engine.responder.api_key)
    if providers != ("local_rules", "local_char_tfidf_demo", "template") or any(keys):
        raise RuntimeError("offline evaluation requires local rules, local TF-IDF, template replies, and no provider API keys")


def _load_cases(path: str | Path) -> tuple[str, int, list[dict[str, Any]]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read evaluation cases: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list) or not payload["cases"]:
        raise ValueError("evaluation suite must contain a non-empty cases list")
    suite = payload.get("suite")
    version = payload.get("version")
    if (
        not isinstance(suite, str)
        or not suite.strip()
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
    ):
        raise ValueError("evaluation suite requires a non-empty suite name and positive integer version")

    seen: set[str] = set()
    for case in payload["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip():
            raise ValueError("each evaluation case requires a non-empty id")
        case_id = case["id"]
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        messages = case.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"case {case_id!r} requires a non-empty messages list")
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or not isinstance(message.get("input"), str) or not message["input"].strip():
                raise ValueError(f"case {case_id!r} message[{index}] requires non-empty input")
            expected = message.get("expect")
            if not isinstance(expected, dict) or not expected:
                raise ValueError(f"case {case_id!r} message[{index}] requires at least one expectation")
            unknown = set(expected) - SUPPORTED_EXPECTATIONS
            if unknown:
                raise ValueError(f"case {case_id!r} message[{index}] has unsupported expectations: {sorted(unknown)}")
            for field, allowed_values in STATUS_EXPECTATIONS.items():
                if field in expected and (not isinstance(expected[field], str) or expected[field] not in allowed_values):
                    raise ValueError(f"case {case_id!r} message[{index}] {field} must be one of {sorted(allowed_values)}")
            checkable = set(expected) - {"order_no", "confirm_action"}
            if not checkable:
                raise ValueError(f"case {case_id!r} message[{index}] requires at least one checkable expectation")
            if "order_no" in expected and (not isinstance(expected["order_no"], str) or not expected["order_no"].strip()):
                raise ValueError(f"case {case_id!r} message[{index}] order_no must be a non-empty string")
            if "order_no" in expected and "order_status" not in expected:
                raise ValueError(f"case {case_id!r} message[{index}] order_no requires order_status")
            if "order_status" in expected and "order_no" not in expected:
                raise ValueError(f"case {case_id!r} message[{index}] order_status requires order_no")
            confirmed_keys = {"confirmed_action_status", "confirmed_order_status"}
            if expected.get("confirm_action"):
                if not {"order_no", "action_status", "order_status", "confirmed_action_status", "confirmed_order_status"}.issubset(expected):
                    raise ValueError(f"case {case_id!r} message[{index}] confirmation requires order and pending/confirmed state expectations")
                if expected["action_status"] != "pending" or expected["order_status"] in {"cancel_requested", "refund_requested"}:
                    raise ValueError(f"case {case_id!r} message[{index}] confirmation requires a pending action and a pre-confirmation order state")
                if expected["order_status"] == expected["confirmed_order_status"]:
                    raise ValueError(f"case {case_id!r} message[{index}] confirmation must expect an order-state transition")
            if confirmed_keys.intersection(expected) and not expected.get("confirm_action"):
                raise ValueError(f"case {case_id!r} message[{index}] confirmed-state expectations require confirm_action")
            if "intent_in" in expected and (not isinstance(expected["intent_in"], list) or not expected["intent_in"] or not all(isinstance(item, str) and item for item in expected["intent_in"])):
                raise ValueError(f"case {case_id!r} message[{index}] intent_in must be a non-empty list of intent names")
            if "required_steps" in expected and (not isinstance(expected["required_steps"], list) or not expected["required_steps"] or not all(isinstance(item, str) and item for item in expected["required_steps"])):
                raise ValueError(f"case {case_id!r} message[{index}] required_steps must be a non-empty list of step names")
            for field in ("route", "contains", "citation_category"):
                if field in expected and (not isinstance(expected[field], str) or not expected[field].strip()):
                    raise ValueError(f"case {case_id!r} message[{index}] {field} must be a non-empty string")
            if "confirm_action" in expected and not isinstance(expected["confirm_action"], bool):
                raise ValueError(f"case {case_id!r} message[{index}] confirm_action must be boolean")
    return suite, version, payload["cases"]


def evaluate(cases_path: str | Path | None = None) -> dict[str, Any]:
    """Run versioned behavior cases using local rules, template replies, and isolated SQLite data."""
    suite, version, cases = _load_cases(cases_path or DEFAULT_CASES)
    dimension_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    results: list[dict[str, Any]] = []
    # tempfile probes its configured directory with os.write on first use; resolve it before blocking OS writes.
    tempfile.gettempdir()

    # Best-effort tripwires for common Python networking APIs; not an OS security sandbox.
    network_attempts: set[str] = set()
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": "", "OPENAI_API_KEY": ""}), ExitStack() as network_guard:
        for owner, name in _network_boundaries():
            target = f"{owner.__name__}.{name}"
            network_guard.enter_context(patch.object(owner, name, _block_network(target, network_attempts)))
        with tempfile.TemporaryDirectory(prefix="shopmate-eval-") as temporary_directory:
            for case_index, case in enumerate(cases):
                engine = DemoEngine(str(Path(temporary_directory) / f"case-{case_index}.sqlite3"))
                _assert_local_providers(engine)
                session = engine.create_session()
                checks: list[dict[str, Any]] = []
                failures: list[str] = []
                observations: list[dict[str, Any]] = []

                for message_index, message in enumerate(case["messages"]):
                    result = engine.handle_message(session["id"], message["input"])
                    expected = message["expect"]
                    actual_intent = result["decision"]["intent"]
                    actual_route = result["trace"]["route"]
                    actual_action = result["actions"][0] if result["actions"] else None
                    order_lookup_step = next((step for step in result["trace"]["steps"] if step["name"] == "order_lookup"), None)
                    order_no_target = (
                        actual_action.get("order_no") if actual_action else
                        order_lookup_step.get("details", {}).get("order_no") if order_lookup_step else None
                    )
                    observation: dict[str, Any] = {
                        "intent": actual_intent,
                        "route": actual_route,
                        "action_status": actual_action["status"] if actual_action else None,
                        "order_no_target": order_no_target,
                        "citation_categories": sorted({item["category"] for item in result["citations"]}),
                        "trace_steps": [step["name"] for step in result["trace"]["steps"]],
                    }

                    def record(dimension: str, passed: bool, description: str) -> None:
                        dimension_counts[dimension]["total"] += 1
                        if passed:
                            dimension_counts[dimension]["passed"] += 1
                        else:
                            failures.append(description)
                        checks.append({"dimension": dimension, "passed": passed, "description": description})

                    prefix = f"message[{message_index}]"
                    if "intent_in" in expected:
                        allowed = expected["intent_in"]
                        record("intent", actual_intent in allowed,
                               f"{prefix}.intent: expected one of {allowed!r}, got {actual_intent!r}")
                    if "route" in expected:
                        route_ok = actual_route == expected["route"]
                        record("route", route_ok,
                               f"{prefix}.route: expected {expected['route']!r}, got {actual_route!r}")
                    if "contains" in expected:
                        contains_ok = expected["contains"] in result["message"]["content"]
                        record("response", contains_ok,
                               f"{prefix}.contains: expected {expected['contains']!r} in assistant response")
                    if "order_no" in expected:
                        order_no_ok = expected["order_no"] in result["message"]["content"]
                        observation["order_no_in_response"] = order_no_ok
                        record("response", order_no_ok,
                               f"{prefix}.order_no: expected {expected['order_no']!r} in assistant response")
                        target_ok = observation["order_no_target"] == expected["order_no"]
                        record("safety", target_ok,
                               f"{prefix}.order_no target: expected {expected['order_no']!r}, got {observation['order_no_target']!r}")
                    if "citation_category" in expected:
                        citation_ok = expected["citation_category"] in observation["citation_categories"]
                        record("retrieval", citation_ok,
                               f"{prefix}.citation_category: expected {expected['citation_category']!r}, got {observation['citation_categories']!r}")
                    if "action_status" in expected:
                        actual_status = observation["action_status"]
                        record("safety", actual_status == expected["action_status"],
                               f"{prefix}.action_status: expected {expected['action_status']!r}, got {actual_status!r}")
                    if "order_status" in expected:
                        order = engine.repository.get_order(expected.get("order_no", ""))
                        actual_status = order["status"] if order else None
                        observation["order_status"] = actual_status
                        record("safety", actual_status == expected["order_status"],
                               f"{prefix}.order_status: expected {expected['order_status']!r}, got {actual_status!r}")
                    if "required_steps" in expected:
                        missing = sorted(set(expected["required_steps"]) - set(observation["trace_steps"]))
                        record("trace", not missing,
                               f"{prefix}.required_steps: missing {missing!r}")
                    if expected.get("confirm_action"):
                        confirmation = engine.repository.confirm_action(actual_action["id"] if actual_action else "")
                        confirmed_action, confirmed_order = confirmation
                        confirmed_action_status = confirmed_action["status"] if confirmed_action else None
                        confirmed_order_status = confirmed_order["status"] if confirmed_order else None
                        requested_action_id = actual_action.get("id") if actual_action else None
                        confirmed_action_id = confirmed_action.get("id") if confirmed_action else None
                        confirmed_action_order_no = confirmed_action.get("order_no") if confirmed_action else None
                        observation["confirmed_action_status"] = confirmed_action_status
                        observation["confirmed_order_status"] = confirmed_order_status
                        action_identity_ok = (
                            confirmed_action is not None
                            and confirmed_action_id == requested_action_id
                            and confirmed_action_order_no == expected["order_no"]
                        )
                        record("safety", action_identity_ok,
                               f"{prefix}.confirmed_action identity: expected id {requested_action_id!r} and order_no {expected['order_no']!r}, got id {confirmed_action_id!r} and order_no {confirmed_action_order_no!r}")
                        if "confirmed_action_status" in expected:
                            confirmed_action_ok = (
                                confirmed_action_status == expected["confirmed_action_status"]
                                and confirmed_action_status != observation["action_status"]
                            )
                            record("safety", confirmed_action_ok,
                                   f"{prefix}.confirmed_action_status: expected transition from {observation['action_status']!r} to {expected['confirmed_action_status']!r}, got {confirmed_action_status!r}")
                        if "confirmed_order_status" in expected:
                            confirmed_order_no = confirmed_order["order_no"] if confirmed_order else None
                            confirmed_order_ok = (
                                confirmed_order_status == expected["confirmed_order_status"]
                                and confirmed_order_no == expected["order_no"]
                            )
                            record("safety", confirmed_order_ok,
                                   f"{prefix}.confirmed_order: expected status {expected['confirmed_order_status']!r} and order_no {expected['order_no']!r}, got status {confirmed_order_status!r} and order_no {confirmed_order_no!r}")
                    observations.append(observation)

                passed_count = sum(1 for check in checks if check["passed"])
                results.append({
                    "id": case["id"],
                    "passed": not failures,
                    "assertions_passed": passed_count,
                    "assertions_total": len(checks),
                    "checks": checks,
                    "failures": failures,
                    "observations": observations,
                })

    if network_attempts:
        attempted = ", ".join(sorted(network_attempts))
        raise RuntimeError(f"offline evaluation blocked attempted network access through: {attempted}")

    passed_cases = sum(1 for case in results if case["passed"])
    total_cases = len(results)
    return {
        "suite": suite,
        "version": version,
        "provider_mode": "offline_demo",
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate": round(passed_cases / total_cases, 4) if total_cases else 0.0,
        "dimensions": dict(sorted(dimension_counts.items())),
        "cases": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ShopMate AI's deterministic offline Agent evaluation suite.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Path to a versioned evaluation JSON file")
    parser.add_argument("--min-pass-rate", type=float, default=1.0, help="Required case pass rate between 0 and 1")
    parser.add_argument("--output", type=Path, help="Optional path for a machine-readable JSON report")
    args = parser.parse_args(argv)
    if not math.isfinite(args.min_pass_rate) or not 0 <= args.min_pass_rate <= 1:
        parser.error("--min-pass-rate must be a finite number between 0 and 1")

    try:
        report = evaluate(args.cases)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Agent eval {report['suite']} v{report['version']}: {report['passed_cases']}/{report['total_cases']} cases passed ({report['pass_rate']:.1%})")
    for dimension, counts in report["dimensions"].items():
        print(f"  {dimension}: {counts['passed']}/{counts['total']}")
    for case in report["cases"]:
        if not case["passed"]:
            print(f"  FAIL {case['id']}")
            for failure in case["failures"]:
                print(f"    - {failure}")
    if args.output:
        print(f"JSON report: {args.output}")
    return 0 if report["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    sys.exit(main())
