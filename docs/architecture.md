# ServiceBrain 技术架构

## 技术栈

### 前端
- **Framework**: Vue 3 + TypeScript
- **Build Tool**: Vite
- **State Management**: Pinia
- **HTTP Client**: Axios
- **WebSocket**: 原生封装

### 后端
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy (Async)
- **Database**: SQLite (Demo) / MySQL (Prod)
- **AI Orchestration**: LangChain
- **Vector Store**: Chroma

## 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      前端表现层                               │
│  ChatView / Components / Stores / Router                     │
└─────────────────────────────────────────────────────────────┘
                            ↓ WebSocket/HTTP
┌─────────────────────────────────────────────────────────────┐
│                      后端接入层                               │
│  WebSocket Handler / HTTP Routes / CORS                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      业务服务层                               │
│  UserService / SessionService / MessageService               │
│  OrchestratorService / RAGService / ToolService              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      AI 编排层                                │
│  LangChain Chains (Intent / Answer / Explain)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      数据持久层                               │
│  SQLite / Chroma Vector Store                                │
└─────────────────────────────────────────────────────────────┘
```

## 核心链路

### 1. 匿名接入链路
```
用户进入 → 用户名输入 → POST /api/v1/user/init-anonymous
      → 创建匿名用户 → 创建会话 → 本地存储 token
      → WebSocket 建连 → 接收首问
```

### 2. 消息处理链路
```
用户消息 → WebSocket → 保存消息 → LangChain 意图识别
      → 路由分流 (知识/解释/Tool) → 生成回复
      → 保存回复 → WebSocket 推送
```

### 3. 记忆管理链路
```
Working Memory (会话内) ←→ Topic Memory (订单级)
      ↓
Session Summary (会话级) ←→ UserProfile (用户级)
```

## 目录结构

详见 [README.md](../README.md#project-structure)

## 状态机

### 页面状态
```
uninitialized → username_input → initializing → chatting
```

### 连接状态
```
disconnected → connecting → connected
                   ↓
              reconnecting → failed
```

### 会话状态
```
creating → active → closed
              ↓
            error
```

## 消息协议

详见 [message.py](../backend/app/schemas/message.py)

## 部署说明

### 开发环境
```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置 API Key
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

### Demo 环境
```bash
# 使用 Docker Compose (待实现)
docker-compose up -d
```

## 当前限制

1. **记忆体系**: 仅实现 Working Memory 和 Topic Memory 基础版
2. **RAG**: 知识库需要手动准备文档
3. **Tool**: 退款 Tool 为 Mock 实现
4. **工单**: 工单系统为简化版，不接真实平台
5. **部署**: 暂不支持一键部署

## 后续演进

1. MySQL 替代 SQLite
2. Redis 缓存 Working Memory
3. 独立 Memory Service
4. 真实 Tool 接入
5. 向量检索优化
