from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Repository:
    """Tiny SQLite store for a self-contained, local-only demo."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[2] / "data" / "demo.sqlite3"
        self.path = Path(db_path or os.getenv("DEMO_DB_PATH", str(default_path)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    trace_json TEXT NOT NULL DEFAULT '{}',
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    actions_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS ix_messages_session_created ON messages(session_id, created_at);
                CREATE TABLE IF NOT EXISTS knowledge (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_no TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_label TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    total_amount REAL NOT NULL,
                    tracking_no TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS products (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    order_no TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    route TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL
                );
                """
            )
            if db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 0:
                self._seed(db)

    @staticmethod
    def _seed(db: sqlite3.Connection) -> None:
        now = utc_now()
        documents = [
            ("kb-after-sales", "演示政策｜退换货规则", "演示资料：常见售后场景可能涉及退货期限、商品完好状态、质量问题处理与凭证要求。具体能否退换、运费由谁承担，应以商家正式政策和订单状态为准；本演示内容不是实际商家承诺。", "after_sales", "演示政策"),
            ("kb-logistics", "演示指南｜发货与物流", "演示资料：订单未发货时可查询预计发货信息；已发货订单应根据物流单号向对应承运方查询轨迹。物流更新可能存在延迟，异常件建议联系人工客服核实。", "logistics", "演示指南"),
            ("kb-payment", "演示指南｜支付与退款到账", "演示资料：退款处理时间取决于商家审核与支付渠道。确认退款状态前不要向用户承诺具体到账时间；若超过商家公布时效，应建立人工工单跟进。", "payment", "演示指南"),
            ("kb-product", "演示指南｜商品与库存信息", "商品的当前价格、规格和库存应以商品服务返回的实时数据为准。知识库只用于解释商品特性和选购建议，不应覆盖实时库存或价格数据。", "product", "演示指南"),
            ("kb-promo", "演示指南｜优惠活动", "促销活动有适用商品、时间和使用门槛。回答活动问题前应查询有效活动配置；未核实的优惠不可承诺。", "promotion", "演示指南"),
            ("kb-security", "服务规范｜身份与隐私核验", "查询订单和处理售后前应校验当前会话用户是否有权访问该订单。不要在回复中展示完整手机号、地址、支付凭证等敏感信息。高风险操作需要用户明确确认，必要时转人工。", "after_sales", "服务规范"),
            ("kb-complaint", "服务规范｜投诉与人工转接", "遇到明确投诉、持续不满、复杂争议或自动化无法核实的事实，应先共情并创建人工跟进请求。演示模式只记录转接意向，不代表真实坐席已接入。", "human", "服务规范"),
        ]
        db.executemany(
            "INSERT INTO knowledge(id,title,content,category,source,version,updated_at) VALUES(?,?,?,?,?,1,?)",
            [(i, t, c, cat, src, now) for i, t, c, cat, src in documents],
        )
        db.executemany(
            "INSERT INTO products(sku,name,category,price,stock,description) VALUES(?,?,?,?,?,?)",
            [
                ("SKU-PHONE-001", "云杉 Note 12 演示手机", "手机", 2399.0, 24, "演示商品：6.7 英寸屏幕，适合日常通讯、学习和影音。规格为演示数据。"),
                ("SKU-AUDIO-002", "雾白无线耳机 演示款", "数码配件", 399.0, 58, "演示商品：支持蓝牙连接和充电盒，适合通勤场景。规格为演示数据。"),
                ("SKU-LAPTOP-003", "青岚轻薄本 演示款", "电脑", 5299.0, 7, "演示商品：轻薄办公本，适合文档、网页和在线会议。规格为演示数据。"),
            ],
        )
        db.executemany(
            "INSERT INTO orders(order_no,product_name,sku,status,status_label,quantity,total_amount,tracking_no,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            [
                ("DEMO20261017001", "云杉 Note 12 演示手机", "SKU-PHONE-001", "shipped", "已发货", 1, 2399.0, "DEMO-TRACK-001", now),
                ("DEMO20261017002", "雾白无线耳机 演示款", "SKU-AUDIO-002", "paid", "已支付，待发货", 1, 399.0, None, now),
                ("DEMO20261017003", "青岚轻薄本 演示款", "SKU-LAPTOP-003", "delivered", "已送达", 1, 5299.0, "DEMO-TRACK-003", now),
            ],
        )

    @staticmethod
    def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def create_session(self, title: str = "新会话") -> dict[str, Any]:
        import uuid
        now, sid = utc_now(), uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)", (sid, title, now, now))
        return {"id": sid, "title": title, "created_at": now, "updated_at": now, "message_count": 0, "status": "active"}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return self.row_dict(row)

    def delete_session(self, session_id: str) -> bool:
        with self.connection() as db:
            cur = db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        return cur.rowcount > 0

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for old, new in (("trace_json", "trace"), ("citations_json", "citations"), ("actions_json", "actions")):
                try:
                    item[new] = json.loads(item.pop(old))
                except (ValueError, TypeError):
                    item[new] = {} if new == "trace" else []
            result.append(item)
        return result

    def add_message(self, session_id: str, role: str, content: str, trace: dict | None = None,
                    citations: list | None = None, actions: list | None = None) -> dict[str, Any]:
        import uuid
        message = {
            "id": uuid.uuid4().hex,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": utc_now(),
            "trace": trace or {},
            "citations": citations or [],
            "actions": actions or [],
        }
        with self.connection() as db:
            db.execute(
                "INSERT INTO messages(id,session_id,role,content,created_at,trace_json,citations_json,actions_json) VALUES(?,?,?,?,?,?,?,?)",
                (message["id"], session_id, role, content, message["created_at"], json_dump(message["trace"]), json_dump(message["citations"]), json_dump(message["actions"])),
            )
            db.execute("UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?", (message["created_at"], session_id))
        return message

    def update_message_actions(self, message_id: str, actions: list[dict[str, Any]]) -> None:
        with self.connection() as db:
            db.execute("UPDATE messages SET actions_json=? WHERE id=?", (json_dump(actions), message_id))

    def recent_messages(self, session_id: str, limit: int = 8) -> list[dict[str, str]]:
        with self.connection() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?", (session_id, limit)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def list_knowledge(self, category: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as db:
            if category:
                rows = db.execute("SELECT * FROM knowledge WHERE category=? ORDER BY updated_at DESC", (category,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM knowledge ORDER BY category,title").fetchall()
        return [dict(row) for row in rows]

    def add_knowledge(self, title: str, content: str, category: str, source: str = "管理员新增") -> dict[str, Any]:
        import uuid
        item = {"id": uuid.uuid4().hex, "title": title, "content": content, "category": category, "source": source, "version": 1, "updated_at": utc_now()}
        with self.connection() as db:
            db.execute("INSERT INTO knowledge(id,title,content,category,source,version,updated_at) VALUES(?,?,?,?,?,?,?)", tuple(item[k] for k in ("id","title","content","category","source","version","updated_at")))
        return item

    def delete_knowledge(self, doc_id: str) -> bool:
        with self.connection() as db:
            cur = db.execute("DELETE FROM knowledge WHERE id=?", (doc_id,))
        return cur.rowcount > 0

    def list_orders(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM orders ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_order(self, order_no: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM orders WHERE order_no=? COLLATE NOCASE", (order_no,)).fetchone()
        return self.row_dict(row)

    def list_products(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM products ORDER BY category,name").fetchall()
        return [dict(row) for row in rows]

    def get_product(self, sku: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM products WHERE sku=? COLLATE NOCASE", (sku,)).fetchone()
        return self.row_dict(row)

    def add_action(self, session_id: str, message_id: str, kind: str, order_no: str) -> dict[str, Any]:
        import uuid
        item = {"id": uuid.uuid4().hex, "type": kind, "order_no": order_no, "status": "pending", "label": "演示待确认：" + ("取消订单" if kind == "cancel_order" else "提交退款申请")}
        with self.connection() as db:
            db.execute("INSERT INTO actions(id,session_id,message_id,type,order_no,status,created_at) VALUES(?,?,?,?,?,'pending',?)", (item["id"], session_id, message_id, kind, order_no, utc_now()))
        return item

    def confirm_action(self, action_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with self.connection() as db:
            action = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if not action:
                return None, None
            if action["status"] == "pending":
                status = "cancel_requested" if action["type"] == "cancel_order" else "refund_requested"
                label = "已提交取消申请（演示）" if action["type"] == "cancel_order" else "已提交退款申请（演示）"
                db.execute("UPDATE actions SET status='confirmed',confirmed_at=? WHERE id=?", (utc_now(), action_id))
                db.execute("UPDATE orders SET status=?,status_label=?,updated_at=? WHERE order_no=?", (status, label, utc_now(), action["order_no"]))
            action = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            order = db.execute("SELECT * FROM orders WHERE order_no=?", (action["order_no"],)).fetchone()
            message_row = db.execute("SELECT actions_json FROM messages WHERE id=?", (action["message_id"],)).fetchone()
            if message_row:
                try:
                    message_actions = json.loads(message_row["actions_json"])
                except (ValueError, TypeError):
                    message_actions = []
                for item in message_actions:
                    if item.get("id") == action_id:
                        item["status"] = action["status"]
                        item["label"] = "取消申请已提交（演示）" if action["type"] == "cancel_order" else "退款申请已提交（演示）"
                db.execute("UPDATE messages SET actions_json=? WHERE id=?", (json_dump(message_actions), action["message_id"]))
        a = dict(action)
        o = self.row_dict(order)
        if a:
            a.pop("session_id", None); a.pop("message_id", None); a.pop("confirmed_at", None); a.pop("created_at", None)
            a["label"] = "取消申请已提交（演示）" if a["type"] == "cancel_order" else "退款申请已提交（演示）"
        return a, o

    def save_trace(self, trace: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO traces(id,session_id,created_at,duration_ms,route,decision_json,steps_json) VALUES(?,?,?,?,?,?,?)",
                       (trace["id"], trace["session_id"], trace["created_at"], trace["duration_ms"], trace["route"], json_dump(trace["decision"]), json_dump(trace["steps"])))

    def list_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM traces ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["decision"] = json.loads(item.pop("decision_json"))
            item["steps"] = json.loads(item.pop("steps_json"))
            items.append(item)
        return items

    def metrics(self) -> dict[str, int]:
        with self.connection() as db:
            return {name: int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for name, table in (("sessions","sessions"),("messages","messages"),("documents","knowledge"),("orders","orders"),("traces","traces"))}
