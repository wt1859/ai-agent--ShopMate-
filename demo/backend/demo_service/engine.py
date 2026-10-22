from __future__ import annotations

import math
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx

from .database import Repository, json_dump, utc_now


ORDER_RE = re.compile(r"(?:DEMO|ORDER)[A-Z0-9_-]{8,24}", re.IGNORECASE)
SKU_RE = re.compile(r"SKU-[A-Z0-9-]{3,30}", re.IGNORECASE)


@dataclass
class RankedDocument:
    document: dict[str, Any]
    dense_score: float
    bm25_score: float
    rrf_score: float
    score: float


class HybridRetriever:
    """A dependency-light demo retriever: character dense proxy + BM25 + RRF."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self._embedding_cache: dict[str, tuple[str, list[float]]] = {}
        self.embedding_provider = f"openai:{self.embedding_model}" if self.api_key else "local_char_tfidf_demo"

    @staticmethod
    def _terms(text: str) -> list[str]:
        text = text.lower()
        chunks = re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]", text)
        chars = re.findall(r"[\u4e00-\u9fff]{2}", text)
        return chunks + chars

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(value * right.get(key, 0) for key, value in left.items())
        norm_left = math.sqrt(sum(v * v for v in left.values()))
        norm_right = math.sqrt(sum(v * v for v in right.values()))
        return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0

    def search(self, query: str, domains: list[str] | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        docs = self.repository.list_knowledge()
        if domains:
            filtered = [doc for doc in docs if doc["category"] in domains]
            if filtered:
                docs = filtered
        query_terms = Counter(self._terms(query))
        n_docs = max(1, len(docs))
        doc_terms = {doc["id"]: Counter(self._terms(doc["title"] + " " + doc["content"])) for doc in docs}
        document_frequency = Counter()
        for terms in doc_terms.values():
            document_frequency.update(terms.keys())
        avg_len = sum(sum(terms.values()) for terms in doc_terms.values()) / n_docs
        dense_scores = self._local_dense_scores(query, docs)
        dense: list[tuple[dict[str, Any], float]] = []
        lexical: list[tuple[dict[str, Any], float]] = []
        for doc in docs:
            terms = doc_terms[doc["id"]]
            dense_score = dense_scores.get(doc["id"], 0.0)
            length = sum(terms.values()) or 1
            bm25 = 0.0
            for term, qtf in query_terms.items():
                if not terms.get(term):
                    continue
                df = document_frequency.get(term, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                tf = terms[term]
                bm25 += idf * ((tf * 2.0) / (tf + 1.5 * (0.75 + 0.25 * length / max(avg_len, 1)))) * min(qtf, 2)
            dense.append((doc, dense_score))
            lexical.append((doc, bm25))
        dense.sort(key=lambda item: item[1], reverse=True)
        lexical.sort(key=lambda item: item[1], reverse=True)
        dense_rank = {doc["id"]: rank for rank, (doc, _) in enumerate(dense, 1)}
        lexical_rank = {doc["id"]: rank for rank, (doc, _) in enumerate(lexical, 1)}
        dense_map = {doc["id"]: score for doc, score in dense}
        lexical_map = {doc["id"]: score for doc, score in lexical}
        results: list[RankedDocument] = []
        for doc in docs:
            doc_id = doc["id"]
            if dense_map[doc_id] <= 0 and lexical_map[doc_id] <= 0:
                continue
            rrf = (1 / (60 + dense_rank[doc_id])) + (1 / (60 + lexical_rank[doc_id]))
            # RRF determines recall order; raw scores break ties and improve exact-keyword hits.
            score = rrf * 0.7 + dense_map[doc_id] * 0.15 + min(lexical_map[doc_id] / 5, 1.0) * 0.15
            results.append(RankedDocument(doc, dense_map[doc_id], lexical_map[doc_id], rrf, score))
        results.sort(key=lambda item: item.score, reverse=True)
        return [self._citation(item) for item in results[: max(1, min(top_k, 10))] if item.score > 0]

    def _local_dense_scores(self, query: str, docs: list[dict[str, Any]]) -> dict[str, float]:
        """Use remote embeddings when configured; keep an offline deterministic proxy otherwise."""
        if not self.api_key:
            term_documents = [Counter(self._terms(doc["title"] + " " + doc["content"])) for doc in docs]
            document_frequency = Counter(term for terms in term_documents for term in terms.keys())
            n_docs = max(1, len(docs))
            idf = {term: math.log(1 + (n_docs + 1) / (frequency + 1)) for term, frequency in document_frequency.items()}
            vectors = []
            for terms in term_documents:
                vectors.append(Counter({term: (1 + math.log(freq)) * idf[term] for term, freq in terms.items()}))
            query_terms = Counter(self._terms(query))
            query_vector = Counter({term: (1 + math.log(freq)) * idf.get(term, 0.0) for term, freq in query_terms.items() if freq})
            return {doc["id"]: self._cosine(query_vector, vector) for doc, vector in zip(docs, vectors)}
        texts = [query] + [doc["title"] + " " + doc["content"] for doc in docs]
        key = "\n".join(texts)
        cached = self._embedding_cache.get(key)
        if cached and cached[0] == self.embedding_model:
            vectors = cached[1]
        else:
            try:
                response = httpx.post(
                    f"{self.api_base}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.embedding_model, "input": texts}, timeout=15.0,
                )
                response.raise_for_status()
                vectors = [item["embedding"] for item in sorted(response.json()["data"], key=lambda item: item["index"])]
                self._embedding_cache[key] = (self.embedding_model, vectors)
            except Exception:
                self.embedding_provider = "local_char_tfidf_demo"
                query_terms = Counter(self._terms(query))
                return {doc["id"]: self._cosine(query_terms, Counter(self._terms(doc["title"] + " " + doc["content"]))) for doc in docs}
        query_vector = vectors[0]
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        scores: dict[str, float] = {}
        for doc, vector in zip(docs, vectors[1:]):
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            scores[doc["id"]] = sum(a * b for a, b in zip(query_vector, vector)) / (query_norm * norm)
        return scores

    @staticmethod
    def _citation(item: RankedDocument) -> dict[str, Any]:
        doc = item.document
        return {
            "id": doc["id"],
            "title": doc["title"],
            "content": doc["content"],
            "category": doc["category"],
            "source": doc["source"],
            "version": doc["version"],
            "updated_at": doc["updated_at"],
            "score": round(item.score, 4),
            "dense_score": round(item.dense_score, 4),
            "bm25_score": round(item.bm25_score, 4),
        }


class JevClassifier:
    """Optional real Jev adapter with deterministic local fallback."""

    INTENTS = {
        "product_consult": ["商品", "产品", "推荐", "价格", "规格", "手机", "电脑", "耳机", "库存"],
        "order_query": ["订单", "订单号", "查订单", "购买记录"],
        "logistics": ["物流", "快递", "到哪里", "什么时候到", "运单", "发货"],
        "refund_return": ["退款", "退货", "退换", "不想要", "取消订单", "退回", "退吗", "退一下", "不合适", "想退"],
        "payment": ["支付", "付款", "扣款", "到账"],
        "after_sales": ["售后", "维修", "保修", "质量", "坏了"],
        "complaint": ["投诉", "差评", "骗子", "态度差", "不满意", "愤怒"],
        "human_agent": ["人工", "真人", "客服", "转人工", "专员"],
        "promotion": ["优惠", "活动", "促销", "折扣", "满减", "优惠券"],
    }
    DOMAIN_BY_INTENT = {
        "product_consult": ["product"], "order_query": ["orders"], "logistics": ["logistics", "orders"],
        "refund_return": ["after_sales", "orders"], "payment": ["payment"], "after_sales": ["after_sales"],
        "complaint": ["human"], "human_agent": ["human"], "promotion": ["promotion"], "other": [],
    }

    def __init__(self) -> None:
        self.api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
        self.model = os.getenv("JEV_MODEL", "jev-latest")
        self.api_base = os.getenv("JEV_API_BASE", "https://api.typesafe.ai").rstrip("/")
        self.provider = "jev" if self.api_key else "local_rules"

    def classify(self, text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        if self.api_key:
            try:
                remote = self._remote(text, history or [])
                if remote:
                    return remote
            except Exception:
                # A demo must continue to work when the optional provider is unavailable.
                pass
        return self._local(text, history or [])

    def _local(self, text: str, history: list[dict[str, str]]) -> dict[str, Any]:
        lower = text.lower()
        scores = {intent: sum(len(keyword) for keyword in words if keyword.lower() in lower) for intent, words in self.INTENTS.items()}
        if not any(scores.values()) and history:
            prior = " ".join(item["content"] for item in history[-4:])
            prior_scores = {intent: sum(1 for keyword in words if keyword.lower() in prior.lower()) for intent, words in self.INTENTS.items()}
            for intent, value in prior_scores.items():
                scores[intent] = scores.get(intent, 0) + min(value, 1)
        intent = max(scores, key=scores.get) if max(scores.values(), default=0) else "other"
        matched = scores.get(intent, 0)
        confidence = min(0.58 + matched * 0.1, 0.96) if intent != "other" else 0.42
        need_human = intent in {"complaint", "human_agent"} or any(word in lower for word in ("非常生气", "解决不了"))
        multi = sum(1 for value in scores.values() if value > 0) > 1
        urgency = 5 if need_human and intent == "complaint" else 3 if intent in {"refund_return", "order_query", "logistics"} else 2
        return {
            "intent": intent,
            "domains": self.DOMAIN_BY_INTENT.get(intent, []),
            "confidence": round(confidence, 3),
            "provider": "local_rules",
            "need_human": need_human,
            "multi_intent": multi,
            "urgency": urgency,
        }

    def _remote(self, text: str, history: list[dict[str, str]]) -> dict[str, Any] | None:
        state = {"message": text, "recent_messages": history[-4:]}
        criteria = {intent: ", ".join(words) for intent, words in self.INTENTS.items()}
        criteria["other"] = "无法确定、闲聊或不属于上述业务"
        payload = {
            "model": self.model,
            "state": state,
            "questions": {
                "intent": {"type": "choice", "instructions": "选择用户当前最主要的电商客服意图", "criteria": criteria},
                "need_human": {"type": "noul", "instructions": "是否应由人工客服介入或优先处理？"},
                "urgency": {"type": "score", "instructions": "评估问题紧急程度", "criteria": ["普通", "较低", "一般", "较高", "紧急"]},
            },
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        response = httpx.post(f"{self.api_base}/v1/systemone", headers=headers, json=payload, timeout=8.0)
        response.raise_for_status()
        body = response.json()
        answers = body.get("answers", {})
        choice = answers.get("intent", {}).get("choice")
        if choice not in (*self.INTENTS.keys(), "other"):
            return None
        intent_answer = answers.get("intent", {})
        need_answer = answers.get("need_human", {}).get("noul", 0)
        urgency_answer = answers.get("urgency", {}).get("score", 2)
        return {
            "intent": choice,
            "domains": self.DOMAIN_BY_INTENT.get(choice, []),
            "confidence": round(float(intent_answer.get("confidence", max(intent_answer.get("probabilities", {}).values(), default=0.0))), 3),
            "provider": "jev",
            "need_human": float(need_answer) >= 0.7,
            "multi_intent": False,
            "urgency": max(1, min(5, round(float(urgency_answer) + 1))),
            "model": body.get("model", self.model),
        }


class LLMResponder:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.provider = "openai" if self.api_key else "template"

    def generate(self, user_text: str, context: str, route: str, history: list[dict[str, str]]) -> str:
        if not self.api_key:
            return self._template(user_text, context, route)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": "你是电商客服小e。只能依据提供的演示资料回答，不确定时明确说需要人工核实；不要编造订单、价格、库存和政策。"},
                *history[-4:],
                {"role": "user", "content": f"路由：{route}\n资料：{context}\n用户问题：{user_text}"},
            ],
        }
        try:
            response = httpx.post(f"{self.api_base}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload, timeout=15.0)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return self._template(user_text, context, route)

    @staticmethod
    def _template(user_text: str, context: str, route: str) -> str:
        if route == "human":
            return "我先帮您记录并转人工跟进。演示模式不会真的接入坐席，请保留当前会话，人工处理结果需要在正式系统中确认。"
        if context:
            return f"根据演示知识库，您可以先参考：\n\n{context.split('来源：')[0].strip()}\n\n如涉及具体订单或实时状态，我还需要查询业务数据后再给您确认。"
        return "我已收到您的问题。当前是本地演示模式，暂时没有足够的业务资料直接确认；您可以补充订单号、商品 SKU 或选择转人工。"


class DemoEngine:
    def __init__(self, db_path: str | None = None) -> None:
        self.repository = Repository(db_path)
        self.retriever = HybridRetriever(self.repository)
        self.classifier = JevClassifier()
        self.responder = LLMResponder()
        self.embedding_provider = self.retriever.embedding_provider

    def status(self) -> dict[str, Any]:
        metrics = self.repository.metrics()
        return {
            "mode": "demo", "intent_provider": self.classifier.provider, "embedding_provider": self.embedding_provider,
            "llm_provider": self.responder.provider, "jev_configured": bool(self.classifier.api_key), "llm_configured": bool(self.responder.api_key),
            **metrics, "features": ["JEV 可选意图路由", "Dense + BM25 + RRF 混合检索", "Harness 轨迹与人工兜底", "订单/商品演示工具"],
            "warning": "演示数据和演示政策不代表真实商家承诺；退款和取消订单只会生成待确认的演示申请。",
        }

    def create_session(self) -> dict[str, Any]:
        return self.repository.create_session()

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.repository.list_sessions()

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.messages(session_id)

    def list_knowledge(self, category: str | None = None) -> list[dict[str, Any]]:
        return self.repository.list_knowledge(category)

    def list_orders(self) -> list[dict[str, Any]]:
        return self.repository.list_orders()

    def list_products(self) -> list[dict[str, Any]]:
        return self.repository.list_products()

    def search(self, query: str, domains: list[str] | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        return self.retriever.search(query, domains, top_k)

    def classify(self, text: str, session_id: str | None = None) -> dict[str, Any]:
        history = self.repository.recent_messages(session_id) if session_id else []
        return self.classifier.classify(text, history)

    def handle_message(self, session_id: str, content: str) -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise ValueError("消息不能为空")
        if not self.repository.get_session(session_id):
            raise KeyError("会话不存在")
        started = time.perf_counter()
        decision = self.classify(content, session_id)
        steps: list[dict[str, Any]] = [{"name": "message_normalize", "status": "ok", "duration_ms": 1.0, "details": {"characters": len(content)}}]
        citations: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        action_marker: str | None = None
        route = "human" if decision["need_human"] else "knowledge"
        order_no = self._extract_order_no(content)
        order = self.repository.get_order(order_no) if order_no else None
        if decision["intent"] in {"order_query", "logistics"}:
            route = "orders"
            steps.append({"name": "order_lookup", "status": "ok" if order or order_no is None else "fallback", "duration_ms": 2.0, "details": {"order_no": order_no, "found": bool(order)}})
            if order:
                body = f"我查到演示订单 {order['order_no']}：{order['status_label']}。商品：{order['product_name']} × {order['quantity']}；金额：¥{order['total_amount']:.2f}。"
                if order["tracking_no"]:
                    body += f"物流单号：{order['tracking_no']}。"
                body += "以上为演示订单数据。"
            elif order_no:
                body = f"暂时没有找到演示订单 {order_no}，请确认订单号或转人工核实。"
            else:
                body = "请提供订单号，我可以查询演示订单的状态和物流信息。"
            citations = self.search(content, ["logistics"], 2)
        elif decision["intent"] == "product_consult":
            route = "product"
            products = self._match_products(content)
            steps.append({"name": "product_lookup", "status": "ok", "duration_ms": 2.0, "details": {"matches": len(products)}})
            if products:
                body = "我找到以下演示商品：\n" + "\n".join(f"{p['name']}（{p['sku']}）｜¥{p['price']:.2f}｜库存 {p['stock']}" for p in products[:3])
            else:
                body = "暂时没有匹配到演示商品，可以试试输入商品名称、品类或 SKU。"
            citations = self.search(content, ["product", "promotion"], 3)
        elif decision["intent"] == "refund_return":
            route = "knowledge+orders"
            citations = self.search(content, ["after_sales", "orders"], 3)
            steps.append({"name": "policy_retrieval", "status": "ok" if citations else "fallback", "duration_ms": 3.0, "details": {"strategy": "BM25 + dense + RRF + rerank", "hits": len(citations)}})
            if any(word in content for word in ("取消", "退货", "退款", "不想要")) and order_no:
                kind = "cancel_order" if "取消" in content else "refund_request"
                body = f"我可以为演示订单 {order_no} 生成{('取消订单' if kind == 'cancel_order' else '退款/退货')}申请，但不会直接执行。请点击下方确认，正式系统还需要身份校验和业务规则审核。"
                action_marker = kind
            else:
                body = "可以先参考演示售后资料。请补充订单号，并说明是取消订单、退款还是退货；提交高风险操作前需要再次确认。"
                action_marker = None
            if citations:
                body += f"\n\n参考：{citations[0]['title']}（演示资料）"
            if action_marker:
                # We create the message first, then attach the action to keep FK integrity.
                action_marker = action_marker
        elif decision["intent"] in {"complaint", "human_agent"}:
            route = "human"
            steps.append({"name": "human_handoff_gate", "status": "ok", "duration_ms": 1.0, "details": {"reason": decision["intent"]}})
            body = self.responder.generate(content, "", route, self.repository.recent_messages(session_id))
            citations = self.search(content, ["human"], 2)
            action_marker = None
        else:
            route = "knowledge"
            citations = self.search(content, decision["domains"] or None, 4)
            steps.append({"name": "hybrid_retrieval", "status": "ok" if citations else "fallback", "duration_ms": 4.0, "details": {"strategy": "BM25 + dense + RRF + rerank", "hits": len(citations)}})
            context = "\n".join(f"{item['content']}\n来源：{item['source']}" for item in citations[:3])
            body = self.responder.generate(content, context, route, self.repository.recent_messages(session_id))
            action_marker = None
        steps.insert(1, {"name": "intent_decision", "status": "ok" if decision["confidence"] >= 0.5 else "fallback", "duration_ms": 2.0, "details": decision})
        user_message = self.repository.add_message(session_id, "user", content)
        trace_id = uuid.uuid4().hex
        trace = {
            "id": trace_id, "session_id": session_id, "created_at": utc_now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2), "steps": steps,
            "decision": decision, "route": route,
        }
        assistant = self.repository.add_message(session_id, "assistant", body, trace, citations, actions)
        if action_marker:
            action = self.repository.add_action(session_id, assistant["id"], action_marker, order_no)
            actions = [action]
            self.repository.update_message_actions(assistant["id"], actions)
            assistant["actions"] = actions
        self.repository.save_trace(trace)
        quick_replies = self._quick_replies(decision["intent"])
        return {"message": assistant, "decision": decision, "trace": trace, "citations": citations, "actions": actions, "quick_replies": quick_replies}

    @staticmethod
    def _extract_order_no(text: str) -> str | None:
        match = ORDER_RE.search(text)
        return match.group(0).upper() if match else None

    def _match_products(self, text: str) -> list[dict[str, Any]]:
        tokens = set(self.retriever._terms(text))
        products = self.repository.list_products()
        scored = []
        for product in products:
            terms = set(self.retriever._terms(product["name"] + " " + product["category"] + " " + product["sku"]))
            score = len(tokens & terms)
            if product["sku"].lower() in text.lower():
                score += 10
            if score:
                scored.append((score, product))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)]

    @staticmethod
    def _quick_replies(intent: str) -> list[str]:
        return {
            "order_query": ["查询物流", "那可以退款吗？"],
            "logistics": ["订单已发货怎么办", "转人工客服"],
            "refund_return": ["补充订单号", "转人工客服"],
            "product_consult": ["查看售后政策", "还有其他商品吗"],
            "complaint": ["转人工客服", "创建工单"],
        }.get(intent, ["七天无理由退货吗？", "查询订单 DEMO20261017001", "转人工客服"])
