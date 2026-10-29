# ShopMate AI Agent 行为评测指南

## 1. 为什么要给 Agent 建回归评测

Agent 的结果不只是一段最终回复。一次请求可能涉及意图判断、上下文、路由、检索、业务工具、用户确认和最终回复。只测“HTTP 返回 200”或“页面能打开”，无法发现这些行为层面的回归：

- 同一条订单问题被路由到了知识问答，而非订单工具；
- 售后回答没有引用政策来源；
- 取消订单在用户确认前改变了订单状态；
- 投诉没有进入人工兜底路线；
- 改动意图关键词后，多轮追问被误判。

因此，ShopMate AI 增加了一组**版本化、离线、确定性**的 Agent 行为样例。它不是模型质量排行榜，也不依赖在线 LLM-as-a-judge；它用明确的业务预期验证当前 Demo 的主要路径，并把容易回归的安全约束纳入检查。

## 2. 评测内容

评测集位于 `demo/backend/evals/cases.json`，当前包含 **8 个合成对话场景**：

| 场景 ID | 覆盖内容 |
|---|---|
| `order_logistics_lookup` | 订单意图、订单路由、演示订单状态和物流知识引用 |
| `product_stock_lookup` | SKU 商品查询、库存返回和商品引用 |
| `after_sales_policy_retrieval` | 售后意图、政策检索与引用 |
| `complaint_human_handoff` | 投诉/人工意图、人工路线和人工兜底步骤 |
| `cancel_requires_confirmation` | 取消订单待确认、确认前状态不变、确认后只改变本地演示状态 |
| `multi_turn_context_followup` | 连续追问中的会话上下文和订单路由 |
| `unknown_intent_fallback` | 未识别意图的安全回退 |
| `promotion_knowledge_retrieval` | 促销路由、检索引用和 trace 步骤 |

评测断言按维度统计：

- **intent**：实际意图是否命中预期候选集合；
- **route**：是否进入正确业务路线；
- **response**：回复中是否包含预期的关键业务提示；
- **retrieval**：是否返回指定知识域的引用；
- **safety**：高风险操作是否待确认、确认前订单状态是否保持、确认后是否只转成演示申请状态；
- **trace**：执行轨迹是否出现要求的步骤。

每个案例各自使用新的 SQLite 临时数据库，避免前一个案例改变后一个案例的数据。运行时会清空 JEV 和 OpenAI API Key 环境变量，并验证分类器、检索器和回复器确实分别使用 `local_rules`、`local_char_tfidf_demo` 和 `template` Provider，且没有配置 Provider Key。默认代码路径使用这些确定性本地 Provider，因此评测不依赖远端模型或 API。评测另外对常见 Python DNS、Socket、TLS 和 OS 写入/转发 API 加装 best-effort tripwire；若经过这些 API 的请求发生，会失败退出。

**边界说明：这些 monkeypatch 是回归防护，不是操作系统级网络沙箱。**它们不能阻止绕过 Python 公共 API 的原生扩展、私有 C 对象访问、子进程或进程外网络访问。因此不得把它们当作运行不可信代码的安全边界；如要求强制零网络出口，应在运行评测的 OS、容器或 CI job 层配置 egress 防火墙/隔离，并单独验证。

## 3. 运行方式

在仓库根目录执行：

```bash
cd demo/backend
uv sync --extra test
uv run python -m demo_service.evaluation --min-pass-rate 1.0
```

期望输出类似：

```text
Agent eval shopmate-offline-agent-regression v1: 8/8 cases passed (100.0%)
  intent: ...
  route: ...
  retrieval: ...
  response: ...
  safety: ...
  trace: ...
```

维度的实际断言数量由评测文件决定；不要把不同版本的断言总数直接当作 Agent 能力提升。

如需保存机器可读报告：

```bash
uv run python -m demo_service.evaluation \
  --min-pass-rate 1.0 \
  --output eval-results/offline-report.json
```

该报告包含套件名、版本、通过场景数、场景通过率、各维度通过数，以及每个案例的预期检查结果/失败原因。报告不记录 API Key，也不请求第三方模型。输出文件是本地运行产物，不要把可能含真实用户信息的线上对话加入案例或提交到公共仓库。

自定义案例文件：

```bash
uv run python -m demo_service.evaluation \
  --cases evals/cases.json \
  --min-pass-rate 0.9
```

`--min-pass-rate` 取值范围是 0 到 1；低于阈值时命令以非零状态退出，适合在 CI 中阻止回归。

## 4. 如何增加评测案例

每个案例代表一个隔离会话；一个案例的 `messages` 可以有多轮输入。示例：

```json
{
  "id": "refund_needs_human_review",
  "messages": [
    {
      "input": "取消订单 DEMO20261017002",
      "expect": {
        "intent_in": ["refund_return"],
        "route": "knowledge+orders",
        "contains": "不会直接执行",
        "action_status": "pending",
        "order_no": "DEMO20261017002",
        "order_status": "paid",
        "confirm_action": true,
        "confirmed_action_status": "confirmed",
        "confirmed_order_status": "cancel_requested"
      }
    }
  ]
}
```

新增案例的建议步骤：

1. 用不含真实个人信息的合成数据描述用户说法；
2. 写清楚正确意图和路线，而不是只检查某个固定措辞；
3. 对业务事实断言工具/数据库返回的状态，对知识回答断言来源类别；
4. 对写操作同时检查确认前与确认后状态；
5. 运行评测和后端测试，确认案例能稳定复现；
6. 若规则或业务契约有意变化，更新版本并解释改变，不要为了让测试变绿而随意放宽标准。

目前支持的断言字段为 `intent_in`、`route`、`contains`、`citation_category`、`action_status`、`order_no`、`order_status`、`required_steps`、`confirm_action`、`confirmed_action_status`、`confirmed_order_status`。

## 5. 这个评测能够证明什么

它可以证明：

- 当前固定离线环境下，选定的业务路径符合写明的断言；
- 主要意图、路由、检索、人工转接和高风险确认行为可以反复回归；
- CI 可执行一条不依赖外部模型服务的质量门禁；
- 测试案例和失败原因可以作为改造前后的工程证据。

## 6. 这个评测不能证明什么

它**不能**证明：

- 真实 JEV、LLM、Embedding 或 MCP 服务效果正确；
- 对任意自然语言、方言、拼写错误或对抗性 Prompt 都可靠；
- 线上准确率、召回率、RAG Faithfulness、人工转接率达到某个数值；
- 系统具备真实 CRM、WhatsApp、订单、支付、物流、身份认证或多租户权限；
- 多轮记忆能跨进程恢复，也不能证明长任务具有 checkpoint、租约、取消传播和幂等恢复；
- 单测/离线评测可以代替安全审查、灰度和真实业务验收。

当前案例是**确定性断言**，而不是模型裁判评价语义质量。若以后接入真实模型，应按 provider 和模型版本记录测试条件，再新增经过人工标注的意图集、检索 Recall@k/MRR、引用忠实度、工具选择率、任务成功率、P95 延迟与成本指标。任何带用户数据的生产轨迹进入评测前，都要做授权、脱敏、保留期限和访问控制。

## 7. 当前项目状态与后续演进

离线评测是对 Agent 工程化的一步，不等于截图所示的所有平台能力都已经完成。后续建议优先建设：

1. **工具目录与策略**：统一工具输入 schema、只读/写入分级、角色授权、审计；之后再接 MCP 协议适配器。
2. **持久 Run 与 SQL Worker**：为长任务加入 Run 状态机、checkpoint、取消、租约、幂等键和受限数据库执行器，验证进程重启后的恢复。
3. **可信记忆与 Context Engineering**：区分用户确认事实、业务 SQL 权威事实、企业知识、推断和短期对话；为来源、时间、租户作用域、有效期和撤销建立规则。
4. **外部可观测性**：在完成脱敏和 trace contract 后，再评估接入 Langfuse/OpenTelemetry。现在的本地 Trace 不是 Langfuse 接入。

优先顺序和“当前做了什么/没有做什么”详见 [`AGENT_ENGINEERING_ROADMAP.md`](AGENT_ENGINEERING_ROADMAP.md)。
