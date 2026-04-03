# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供操作本代码仓库的指引。

## 项目概述

ServiceBrain 是一个 AI 驱动的智能客服机器人平台，采用 Vue 3 前端 + Python FastAPI 后端架构。系统使用 LangChain 进行 AI 编排，并实现了多层级记忆系统用于对话上下文管理。

## 开发命令

### 后端 (Python)

```bash
cd backend

# 环境初始化
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑配置你的 API 密钥

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试
pytest                              # 运行所有测试
pytest tests/test_api.py           # 仅 API 测试
pytest tests/test_services.py      # 仅服务层测试
pytest -k "test_name"              # 按名称运行单个测试
pytest -v                          # 详细输出模式

# API 文档（服务运行后访问）
# http://localhost:8000/docs
```

### 前端 (Vue 3 + TypeScript)

```bash
cd frontend

# 环境初始化
npm install
cp .env.example .env

# 启动开发服务器
npm run dev     # http://localhost:5173

# 构建
npm run build
npm run preview
```

### E2E 测试 (Playwright)

```bash
cd e2e

# 环境初始化
npm install
npx playwright install

# 运行测试
npm run test:e2e           # 运行所有测试
npm run test:e2e:ui        # 带 UI 界面运行
npm run test:e2e:debug     # 调试模式
npm run test:e2e:report    # 查看测试报告
```

## 架构概览

### 后端结构

后端采用分层架构：

1. **API 层** (`app/api/`)
   - `http_routes.py`: 用户/会话初始化的 REST 接口
   - `ws_routes.py`: 实时聊天的 WebSocket 处理器

2. **服务层** (`app/services/`)
   - `orchestrator_service.py`: **核心编排中心** - 协调所有服务，处理消息路由、意图识别、槽位填充和漂移检测
   - `memory_service.py`: 管理工作记忆和主题记忆
   - `rag_service.py`: 基于 Chroma 的知识库检索
   - `llm_service.py`: LLM 客户端（默认：通义千问 via DashScope）
   - `tool_service.py`: 工具执行（如退款处理）
   - `rule_service.py`: 业务规则评估
   - `ticket_service.py`: 人工升级工单创建

3. **链层** (`app/chains/`)
   - `intent_chain.py`: 基于 LLM 的意图识别

4. **数据层** (`app/models/`)
   - SQLAlchemy 异步模型：User, Session, Message, Memory, Ticket, ToolRecord

### 关键架构模式

**OrchestratorService** (`app/services/orchestrator_service.py:34-1103`) 是中央协调器：

- 通过 `process_user_message()` 接收所有用户消息
- 使用 LLM 执行意图识别
- 处理槽位填充（如缺少 order_id 时进行询问）
- 路由到对应处理器：refund_execute、refund_explain、refund_consult、logistics、presale、knowledge_answer
- 返回结构化响应字典，最终转为机器人消息

**记忆系统**：

- 工作记忆 (Working Memory)：会话级上下文（当前主题、任务、待填充槽位、订单号）
- 主题记忆 (Topic Memory)：跨会话的订单级持久记忆
- 当消息超过 10 条或检测到强漂移时触发上下文压缩

**消息协议** (`app/schemas/message.py`)：

- WebSocket 消息使用结构化 JSON，包含 `type`、`message_id`、`session_id`、`payload`
- 卡片消息（tool_result_card、ticket_card）包含用于 UI 按钮的 actions 数组

### 前端结构

- **状态管理**：`src/stores/` 中的 Pinia 状态库
- **API 客户端**：`src/api/index.ts` - HTTP 接口
- **WebSocket**：`src/views/ChatView.vue` 中的原生 WebSocket，带 ping/pong 心跳
- **组件**：消息渲染同时支持文本和卡片类型

### 配置

后端配置位于 `app/core/config.py`，使用 Pydantic Settings：

- `LLM_*`：LLM 提供商配置（默认：通义千问/DashScope）
- `DATABASE_URL`：演示用 SQLite，生产用 MySQL
- `CHROMA_PERSIST_DIR`：向量存储位置
- `MAX_CONTEXT_MESSAGES`：工作记忆窗口大小

## 测试

### 后端测试

- 使用 pytest 配合异步支持（pytest-asyncio）
- 测试数据库：SQLite 内存模式（`sqlite+aiosqlite:///:memory:`）
- `conftest.py` 中的 fixtures 提供 test_db、test_client 及依赖覆盖

### E2E 测试

- Playwright 测试位于 `e2e/tests/`
- 测试假设服务运行在 localhost:5173（前端）和 localhost:8000（后端）
- 测试数据规则：订单号以 1 开头=成功，2=超时，3=系统故障

## 重要实现细节

**意图识别流程**：

1. LLM 识别意图（主题、任务、缺失槽位、是否主题漂移等）
2. 如果存在 pending_slot 且未检测到漂移 → 填充槽位并继续原任务
3. 如果检测到漂移 → 清除 pending_slot 并使用新意图

**退款工具模拟行为** (`app/services/tool_service.py`)：

- 订单号以 "1" 开头 → 成功
- 以 "2" 开头 → 不允许（超时）
- 以 "3" 开头 → 失败（系统错误）
- 其他 → 随机结果

**RAG 服务** (`app/services/rag_service.py`)：

- 使用 Chroma 向量存储
- 文档从 `data/knowledge/` 目录加载
- 如未找到相关文档则降级为 LLM 直接回答

## 环境初始化要求

- Python 3.12+（后端）
- Node.js 18+（前端）
- 在 `backend/.env` 中配置通义千问 API 密钥：`LLM_API_KEY=your_key_here`
