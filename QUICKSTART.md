# ServiceBrain 快速开始指南

## 5 分钟启动 Demo

### 方式一：一键启动（推荐）

```bash
cd ServiceBrain
./start.sh
```

访问 http://localhost:5173

### 方式二：分步启动

#### 1. 启动后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY

# 创建数据目录
mkdir -p data knowledge

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 2. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173

---

## 配置说明

### 后端 .env

```bash
# LLM 配置（必须）
LLM_API_KEY=sk-kimi-your-api-key-here

# 数据库（可选，默认 SQLite）
DATABASE_URL=sqlite+aiosqlite:///./data/servicebrain.db

# 其他配置通常无需修改
```

### 前端 .env

通常无需修改，使用默认配置即可。

---

## 演示流程

1. **首次进入** → 输入用户名（如"王先生"）
2. **接收首问** → "你好，王先生，我是你的智能客服助手..."
3. **测试知识问答** → 发送"退款多久到账？"
4. **测试退款执行** → 发送"帮我退款"
   - 系统追问订单号
   - 输入 `10001` → 成功卡片
   - 输入 `10002` → 不可执行卡片
   - 输入 `10003` → 失败卡片
5. **测试工单兜底** → 点击失败卡片的"提交跟进请求"

---

## 常见问题

### Q: 后端启动失败？

A: 检查：
- Python 版本 >= 3.11
- 虚拟环境已激活
- 依赖已安装：`pip install -r requirements.txt`

### Q: 前端启动失败？

A: 检查：
- Node.js 版本 >= 18
- 依赖已安装：`npm install`

### Q: WebSocket 连接失败？

A: 检查：
- 后端是否在 8000 端口运行
- 防火墙是否阻止连接

### Q: API 调用失败？

A: 检查：
- 后端日志是否有错误
- .env 配置是否正确

---

## 下一步

- 查看 [README.md](./README.md) 了解项目详情
- 查看 [docs/architecture.md](./docs/architecture.md) 了解技术架构
- 开始开发你的功能！
