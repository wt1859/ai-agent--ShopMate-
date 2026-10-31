# ShopMate AI｜电商客服 Agent 运行时与长期记忆系统

**把客服对话拆解为可观察、可评测、受控执行的 Agent 工作流。**

## 项目简介

ShopMate AI 是一个面向 AI Agent 工程实践的全栈 Demo。项目没有把所有请求简单交给聊天模型，而是围绕电商客服中的真实问题类型，设计了一套从用户消息进入、意图判断、业务路由、知识检索、结构化工具调用、风险确认、回复组装到执行轨迹持久化的完整处理链路。

系统重点覆盖订单查询、物流进度、商品咨询、库存确认、售后政策、退款/取消申请、投诉和人工转接等场景。订单、商品、库存和物流等业务事实由本地 SQLite 演示数据与受控业务工具提供；售后、促销等政策问题由带来源的知识检索提供证据；短期对话上下文由会话管理维护；Mem0 仅作为可选的用户长期偏好记忆，不承担订单或交易事实存储。

项目定位为**可本地运行、可离线评测、可观察和可回归验证的 Agent 工程 Demo**，不是已经接入真实 CRM、支付、物流或线上客户数据的生产客服平台。

### 项目基本信息

- **项目类型：**独立开发 / AI Agent 全栈 Demo
- **项目角色：**AI Agent 工程实现、后端与前端全栈开发
- **核心技术：**Python、FastAPI、SQLite、Vue 3、TypeScript、Vite、Mem0、pytest、Vitest、uv
- **运行方式：**本地启动，默认不依赖外部 LLM、Embedding、Mem0 或有效认证
- **可运行目录：**[`demo/`](demo/)

## 项目亮点

- **电商客服 Agent 工作台：**面向订单、商品、库存、物流、售后政策和投诉转人工等客服场景，将会话管理、意图识别、业务路由、知识检索、订单/商品查询、操作确认和执行记录组织成完整链路，形成从用户请求到业务处理结果的可追踪闭环。
- **Agent Runtime 与 Harness 编排：**将消息规范化、短期上下文组装、可选长期记忆检索、意图决策、流程路由、知识/工具调用、回复组装和 Trace 持久化拆分为明确步骤；每轮执行记录 `decision`、`route`、`steps`、`citations` 与耗时，出现问题时可以定位到意图、检索、业务工具、人工兜底或记忆服务环节，而不是只能查看最终回复。
- **意图路由与业务事实分层：**围绕订单查询、物流查询、商品咨询、售后退款、投诉和人工服务建立显式业务路线；默认使用本地规则识别意图，也保留可选 JEV 适配器；订单、商品和库存通过 Repository 查询结构化数据，政策类问题进入知识检索，避免让模型凭对话上下文猜测实时业务状态。
- **混合检索与知识引用：**针对售后、物流和促销政策表达多样，以及订单号、SKU 等标识符需要精确匹配的特点，组合 BM25 风格词法检索、字符 TF-IDF 相似度和 RRF 排序；检索结果保留知识分类、来源、版本、更新时间和分数，并将引用同步到回复与 Trace，使答案既能匹配不同表达，也能追溯回答依据。
- **高风险操作与确认控制：**将取消订单、退款和退货从普通查询流程中分离，设计 `pending → confirmed` 操作状态；用户确认前不修改订单状态，确认后只更新本地演示数据并保留操作记录，避免一次模型或规则判断直接触发高风险业务写入。
- **Mem0 长期记忆与隐私边界：**接入可选 Mem0 Platform / OSS 适配层，按 `customer_id/user_id + agent_id` 隔离用户偏好，支持跨会话召回历史选择；只提交筛选后的用户偏好候选，在 SDK 调用前拦截密码、密钥、联系方式、地址、订单标识和交易内容，并将写入结果区分为 `skipped`、`no_change`、`accepted`、`pending`、`unknown` 和 `error`。
- **离线降级与 Provider 适配：**默认使用本地规则、模板回复、SQLite 演示数据和字符 TF-IDF 检索代理完成离线闭环；JEV、OpenAI-compatible LLM、Embedding 以及 Mem0 均通过可选适配器接入，外部服务异常时回退到本地实现，不阻塞普通客服流程，且不把本地替身描述为真实远端能力。
- **Agent Eval 与回归保护：**维护 8 个合成对话场景和 45 项确定性断言，覆盖意图、路由、回复、知识引用、Trace、多轮上下文和取消确认前后状态；离线评测结果为 8/8，后端测试 124 项通过，前端测试 20 项通过，生产构建成功，并由 GitHub Actions 自动执行后端测试、离线评测、前端测试和构建。

## 核心处理流程

```text
用户消息
   ↓
会话 / customer_id
   ↓
敏感信息与交易内容筛选 → 可选 Memory search
   ↓
意图判断与置信度决策
   ├── 订单 / 商品 / 库存 / 物流 → SQLite 业务工具
   ├── 售后 / 促销 / 政策 → 混合知识检索 + 来源引用
   ├── 退款 / 取消 → Human-in-the-loop 确认门
   ├── 投诉 / 转人工 → 人工兜底路线
   └── 未知问题 → 知识检索或安全回退
   ↓
回复组装 + 引用展示
   ↓
偏好候选筛选与可选 Memory write
   ↓
Trace 持久化：decision / route / steps / citations / latency
```

## 系统架构

```text
Vue 3 / TypeScript 客服工作台
        ↓
FastAPI API 层：会话、Chat、知识、订单、商品、确认、Trace、状态
        ↓
Agent Harness：消息规范化 → Memory → Intent → Route → Retrieve/Tool
        ↓
决策与检索模块：本地规则 / 可选 JEV / BM25 风格匹配 / TF-IDF / RRF
        ↓
SQLite 业务事实与 Trace ─── 可选 Mem0 用户长期偏好
```

这里的职责是分开的：意图模块判断用户想做什么，Harness 控制流程，检索系统查找政策证据，业务工具读取订单和商品事实，确认模块阻断高风险写入，LLM（如果配置）只负责可选的决策或自然语言组织。

> **可运行 Demo 位于 [`demo/`](demo/)。** 仓库中早期的 `backend/`、`frontend/`、`config/`、`docker/` 等骨架目录尚未补全，不属于这个可运行版本。订单、商品和知识数据为本地演示数据，不连接真实电商服务。

## 快速开始（Windows）

需要安装 [uv](https://docs.astral.sh/uv/) 和带 npm 的 Node.js。双击 [`demo/start-demo.bat`](demo/start-demo.bat)，首次运行时脚本会准备依赖并在需要时构建前端。

启动后打开 <http://localhost:8765>。保持启动窗口运行；停止服务时在该窗口按 `Ctrl+C`。

### 手动启动

```bash
cd demo/frontend
npm ci
npm run build

cd ../backend
uv sync
uv run uvicorn app:app --app-dir . --host 127.0.0.1 --port 8765
```

接口地址：

- 页面：<http://localhost:8765>
- API 文档：<http://localhost:8765/api/docs>
- 健康检查：<http://localhost:8765/health>
- Demo 状态：<http://localhost:8765/api/demo/status>

更多说明见 [`demo/README.md`](demo/README.md)。

## 试试这些问题

```text
查询订单 DEMO20261017001 的物流
SKU-PHONE-001 有库存吗？
七天无理由退货吗？
取消订单 DEMO20261017002
投诉，转人工客服
```

## 运行测试

后端（在 `demo/backend` 目录）：

```bash
uv sync --extra test
uv run pytest tests -q
```

前端（在 `demo/frontend` 目录）：

```bash
npm ci
npm test -- --run
npm run build
```

## Mem0 长期记忆

已提供 Mem0 Platform 和 OSS 适配器、跨会话用户作用域、偏好写入筛选、回复与 Trace 展示。默认 `MEMORY_PROVIDER=disabled`，不会自动发送对话到外部服务。

启用步骤和验证边界见 [Mem0 接入说明](demo/MEM0.md)。需要本地配置服务凭据或自部署模型；单元测试中的外部服务替身不代表真实 Mem0 已联网验证。

## 模型配置与密钥

不配置任何模型服务也能运行完整的离线 Demo。若要实验外部服务，复制 `demo/.env.example` 为 `demo/.env`，再按所选服务商填写配置。密钥只保存在本地 `.env` 中，切勿提交到 GitHub。

环境变量被读取不代表远端调用一定成功；应通过 `/api/demo/status` 和单次请求的执行轨迹核实当前实际使用的 provider。API 可用性、费用和模型效果由相应服务商决定。

## 项目边界

这是一个学习用业务闭环 Demo，不是生产客服系统：

- 订单、商品和知识条目都是 SQLite 演示数据，不连接真实电商、支付或物流系统。
- 取消和退款确认只更新本地演示数据，不会真正退款或取消订单。
- 默认使用本地规则、模板回复和字符 TF-IDF 检索代理；这不等于真实 JEV、LLM 或生产向量检索。
- 未实现生产所需的用户认证、权限校验、数据脱敏、审计、限流、监控和人工坐席集成。
- 仓库历史骨架仍保留在你的本地目录中，但因许多模块为空或未完成，不纳入本次发布版本。

## Documentation

- [详细技术报告](docs/TECHNICAL_REPORT.md)：技术选型、Agent 组件边界、流程、验证和 Demo 边界。
- [Agent 行为评测指南](docs/EVALUATION_GUIDE.md)：介绍离线回归案例、运行命令、断言维度和评测边界。
- [Demo 运行说明](demo/README.md)

## Agent 行为评测

在 `demo/backend` 执行：

```bash
uv sync --extra test
uv run python -m demo_service.evaluation --min-pass-rate 1.0
```

评测以本地规则、模板和 SQLite 演示数据离线运行，覆盖 8 个合成对话场景；它不是线上准确率或真实模型效果指标。GitHub Actions 会自动运行后端测试、离线评测、前端测试和生产构建。

## License

本项目采用 [MIT License](LICENSE)。

---

**English summary:** ShopMate AI is a full-stack e-commerce Agent Runtime demo for learning and engineering practice. It turns customer messages into observable workflows covering intent routing, cited knowledge retrieval, SQLite-backed demo tools, human confirmation for risky actions, and execution traces. Its offline regression suite includes 8 synthetic conversations and 45 deterministic checks. The app runs locally; it does not connect to production CRM, commerce, payment, or logistics systems.
