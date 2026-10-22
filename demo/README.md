# ShopMate AI Demo

用于学习电商智能客服 Agent 架构的本地 Demo。当前可运行应用由 Vue 3 + TypeScript 前端和 FastAPI 后端组成，默认使用本地规则、模板回复、混合检索代理和 SQLite 演示数据。

> 这是学习/演示项目，不连接真实订单、支付或物流系统。退款和取消操作经确认后也只更新本地演示数据库。

## Windows 快速启动

安装 [uv](https://docs.astral.sh/uv/) 和带 npm 的 Node.js 后，双击 `start-demo.bat`。首次运行会准备后端依赖；如果前端还没有构建产物，启动脚本会安装前端依赖并构建页面。

打开 <http://localhost:8765>。停止时在启动窗口按 `Ctrl+C`。

## 手动启动

在仓库根目录执行：

```bash
cd demo/frontend
npm ci
npm run build

cd ../backend
uv sync
uv run uvicorn app:app --app-dir . --host 127.0.0.1 --port 8765
```

## 常用地址

- 页面：<http://localhost:8765>
- API 文档：<http://localhost:8765/api/docs>
- 健康检查：<http://localhost:8765/health>
- Demo 状态：<http://localhost:8765/api/demo/status>

## 测试

后端（从 `demo/backend` 运行）：

```bash
uv sync --extra test
uv run pytest tests -q
```

前端（从 `demo/frontend` 运行）：

```bash
npm ci
npm test -- --run
npm run build
```

## 演示输入

```text
查询订单 DEMO20261017001 的物流
SKU-PHONE-001 有库存吗？
七天无理由退货吗？
取消订单 DEMO20261017002
投诉，转人工客服
```

也可以先问“商品不合适，可以退吗？”，再追问“那订单已经发货了呢？”，观察会话上下文如何参与路由。

## 可选模型实验

离线模式不需要密钥。需要尝试外部服务时，把 `.env.example` 复制为此目录下的 `.env`，再填写 JEV 或 OpenAI-compatible 服务配置。密钥不要提交到仓库。

当前状态接口展示配置/provider 信息，不保证远端调用成功。请通过实际请求的执行轨迹检查是否发生了模型调用，以及失败后是否回退到本地实现。

## 能力边界

- 数据库存储使用 SQLite 和种子演示数据。
- 默认意图识别是本地规则；默认回复是模板。
- 默认“dense”检索是字符 TF-IDF 演示代理，不是真实 embedding 模型或向量数据库。
- 取消/退款只生成演示申请，不连接真实交易系统。
- 生产环境需要另外实现身份与权限校验、隐私保护、审计、限流、监控、真实业务接口和人工坐席流程。
