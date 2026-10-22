# ShopMate AI

**ShopMate AI** 是一个用于学习电商智能客服 Agent 架构的本地 Demo。它把一条客服请求拆成意图判断、流程路由、知识检索或业务工具调用，再生成回复并记录执行轨迹，方便观察 Agent 每一步做了什么。

> **当前可运行版本在 [`demo/`](demo/)。** 本地原始目录中的 `backend/`、`frontend/`、`config/`、`docker/`、`docs/` 等，是尚未补全的早期项目骨架或参考资料，不属于可运行应用，本次 GitHub 发布只包含 `demo/` 和项目说明。

## 这个项目能做什么

- 在客服工作台中创建会话并发送消息。
- 识别物流、订单、商品、售后和人工服务等常见意图。
- 根据意图选择知识库检索或演示业务工具。
- 查看回复引用、工具结果和 Harness 执行轨迹。
- 管理演示知识条目，查看订单和商品样例。
- 对退款/取消订单请求执行确认流程，观察高风险操作的安全边界。
- 默认离线运行；可选配置 JEV 兼容接口和 OpenAI-compatible 聊天/Embedding 接口用于学习。

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

- [详细技术报告](docs/TECHNICAL_REPORT.md)：传统客服对比、技术选型原因、Agent 技术清单、请求流程、接口、边界和学习路线。
- [Demo 运行说明](demo/README.md)

## License

本项目采用 [MIT License](LICENSE)。

---

**English summary:** ShopMate AI is a locally runnable educational e-commerce customer-service agent demo. It shows intent routing, a lightweight Harness runtime, hybrid knowledge retrieval, mock business tools, confirmations for risky actions, and execution traces. The runnable app is in `demo/`; it uses sample data and is not production-ready.
