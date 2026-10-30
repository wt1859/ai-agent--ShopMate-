# ShopMate AI | 电商客服 Agent Runtime

**把客服对话变成一条可观察、可评测、受控执行的 Agent 工作流。**

ShopMate AI 是一个面向 AI Agent 开发求职展示的全栈工程 Demo。它演示 Agent 如何从用户消息中识别意图、选择业务路线、检索带来源的知识、调用订单/商品工具，并在取消或退款等高风险操作前等待用户确认。每轮执行都会留下 Trace；配套离线评测集用合成对话检查路由、回复、引用、安全状态和执行步骤。

当前版本基于 Vue 3、TypeScript、FastAPI 和 SQLite，可在本地离线运行。重点不是堆一个聊天页面，而是把 Agent 的控制流、工具边界、安全门和回归验证做成可以运行、阅读和测试的代码。

> **可运行 Demo 位于 [`demo/`](demo/)。** 仓库中早期的 `backend/`、`frontend/`、`config/`、`docker/` 等骨架目录尚未补全，不属于这个可运行版本。订单、商品和知识数据为本地演示数据，不连接真实电商服务。

## 工程亮点

- **显式 Agent 控制流**：把意图识别、业务路由、检索/工具调用、风险确认、回复和 Trace 串成可读的执行链，而不是只返回一段聊天文本。
- **知识与业务事实分开**：政策类问题走混合检索并展示引用；订单、商品和库存问题读取 SQLite 演示数据，避免把实时业务事实交给模型猜。
- **高风险操作有确认门**：取消/退款先创建 `pending` 操作，用户确认后才改变本地演示状态；测试覆盖确认前后状态。
- **行为可回归**：包含 8 个合成对话场景、45 项确定性断言，覆盖意图、路由、回复、检索、安全与 Trace；评测失败会返回非零状态，供 CI 使用。
- **完整全栈闭环**：Vue 3 + TypeScript 工作台、FastAPI 服务、SQLite 数据、后端/前端测试和 GitHub Actions 工作流。
- **Provider 可替换但不冒充已接入**：默认使用本地规则、模板和字符 TF-IDF 检索代理；仓库保留可选接口用于学习，真实模型效果需要用户自行配置并验证。

## 架构概览

```text
用户消息
   ↓
Vue 客服工作台
   ↓
FastAPI / Harness 运行时
   ↓
意图判断与流程路由（默认本地规则，可选 JEV）
   ├── 知识问题 → BM25 + 本地字符 TF-IDF 代理 → 引用与回复
   ├── 订单/商品 → SQLite 演示业务工具 → 查询结果
   └── 退款/取消 → 待确认操作 → 更新本地演示数据
   ↓
模板回复（可选 OpenAI-compatible LLM）+ 执行轨迹
```

这里的职责是分开的：意图模型判断用户想做什么，Harness 控制流程，检索系统查找知识，业务工具读取演示数据，LLM（如果配置）负责组织自然语言回复。

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
- [Agent 求职工程路线图](docs/AGENT_ENGINEERING_ROADMAP.md)：把参考岗位能力映射到本项目，区分已实现、未实现和下一步计划，并提供真实可用的项目表述。
- [Agent 行为评测指南](docs/EVALUATION_GUIDE.md)：介绍离线回归案例、运行命令、断言维度和评测边界。
- [Demo 运行说明](demo/README.md)

## Agent 行为评测

在 `demo/backend` 执行：

```bash
uv sync --extra test
uv run python -m demo_service.evaluation --min-pass-rate 1.0
```

评测以本地规则、模板和 SQLite 演示数据离线运行，覆盖 8 个合成对话场景；它不是线上准确率或真实模型效果指标。GitHub Actions 会自动运行后端测试、离线评测、前端测试和生产构建。

## 面向 AI Agent 开发岗位的项目说明

这个项目可以展示 Agent 控制流、工具/检索边界、Human-in-the-loop、Trace 和离线回归评测。项目简介、面试讲解和后续路线见 [Agent 求职工程路线图](docs/AGENT_ENGINEERING_ROADMAP.md)。

**简历表述边界：**这是独立学习用的本地 Demo；目前没有真实 CRM、WhatsApp、MCP 协议、持久化分布式 Run、Langfuse、真实订单/支付系统或线上客户数据。不要把路线图中的规划写成已经落地的生产经验。

## License

本项目采用 [MIT License](LICENSE)。

---

**English summary:** ShopMate AI is a full-stack e-commerce Agent Runtime demo for learning and portfolio use. It turns customer messages into observable workflows covering intent routing, cited knowledge retrieval, SQLite-backed demo tools, human confirmation for risky actions, and execution traces. Its offline regression suite includes 8 synthetic conversations and 45 deterministic checks. The app runs locally; it does not connect to production CRM, commerce, payment, or logistics systems.
