# ServiceBrain 🧠

**Intelligent Customer Service Robot Platform**  
**智能客服机器人平台**

---

## Overview

ServiceBrain is an AI-powered customer service robot platform designed for enterprise-scale intelligent customer service scenarios.

ServiceBrain 是一个面向企业级智能客服场景的 AI 驱动客服机器人平台。

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- npm or pnpm

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Access

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Features

- 🤖 **Multi-turn Dialogue** - 多轮对话管理
- 🧠 **Intent Recognition** - 意图识别与理解
- 📊 **Analytics Dashboard** - 数据分析看板
- 🔌 **Plugin Architecture** - 插件化架构
- 🌐 **Multi-channel Support** - 多渠道接入（Web/App/电话/微信）

## Tech Stack

### Frontend
- **Framework**: Vue 3 + TypeScript
- **Build Tool**: Vite
- **State Management**: Pinia
- **WebSocket**: Native封装

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy
- **Database**: SQLite (Demo) / MySQL (Prod)
- **AI Orchestration**: LangChain
- **Vector Store**: Chroma

## Project Structure

```
ServiceBrain/
├── backend/              # Python FastAPI 后端
│   ├── app/
│   │   ├── api/         # HTTP/WebSocket 接口
│   │   ├── core/        # 配置/日志
│   │   ├── models/      # SQLAlchemy 模型
│   │   ├── schemas/     # Pydantic 协议
│   │   ├── repositories/# 数据访问层
│   │   ├── services/    # 业务服务层
│   │   ├── chains/      # LangChain 编排
│   │   └── vectorstore/ # 向量库
│   ├── data/            # 知识库文档
│   ├── tests/
│   └── requirements.txt
├── frontend/            # Vue 3 前端
│   ├── src/
│   │   ├── api/        # API 客户端
│   │   ├── components/ # 消息组件
│   │   ├── stores/     # Pinia Stores
│   │   ├── views/      # 页面
│   │   ├── types/      # TypeScript 类型
│   │   └── utils/      # 工具函数
│   └── package.json
└── docs/               # 技术文档
```

## Architecture

详见 [docs/architecture.md](./docs/architecture.md)

## License

MIT License

---

*Built with ❤️ by Wayne*
