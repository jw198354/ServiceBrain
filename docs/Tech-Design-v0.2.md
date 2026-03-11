# 电商客服咨询场景 H5 智能客服机器人 Demo 
# 详细技术设计方案文档（V0.2）

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | 电商客服咨询场景 H5 智能客服机器人 Demo 详细技术设计方案 |
| 项目名称 | H5 智能客服机器人 Demo |
| 版本号 | V0.2 |
| 作者 | 技术架构设计 |
| 评审对象 | 产品、前端、后端、AI 应用、测试 |
| 更新时间 | 2026-03-10 |
| 文档状态 | 技术设计评审稿 |
| 适用阶段 | Demo 研发启动 / 技术评审 / 开发联调 |

### 1.1 修订记录

| 版本 | 日期 | 修订人 | 内容 |
|---|---|---|---|
| V0.1 | 2026-03-10 | 架构设计 | 首版详细技术设计方案输出 |
| V0.2 | 2026-03-10 | 架构设计 | 合并记忆体系设计，补充上下文隔离、压缩、历史检索、意图漂移控制 |

---

## 2. 设计背景与目标

### 2.1 产品背景

当前需建设一个面向电商客服咨询场景的 H5 智能客服机器人 Demo，用于完整展示以下能力闭环：

- 匿名低门槛接入
- WebSocket 实时聊天
- 机器人主动首问
- 用户自然表达问题
- AI 理解与问题/诉求联合识别
- 槽位补齐与多轮追问
- 纯知识答疑
- 规则解释答疑
- 退款执行类工具调用
- 异常兜底与工单引导

本期目标不是打造完整生产级客服平台，而是用尽量轻量的技术架构快速跑通核心业务链路，并保留后续扩展空间。

### 2.2 技术建设目标

本方案需要满足以下技术目标：

1. 快速支撑 Demo 开发和现场演示。 
2. 以最小复杂度跑通真实业务闭环。 
3. AI 理解、RAG、规则判断、Tool 调用之间边界清晰。 
4. 页面状态与系统状态能够稳定映射。 
5. 系统在断连、AI 失败、RAG 无结果、工具失败时具备可恢复或可兜底能力。 
6. 在重复进线咨询场景下，具备基础历史承接能力。 
7. 通过轻量记忆体系解决上下文隔离、压缩和意图漂移问题。 

### 2.3 当前阶段设计原则

#### 原则一：轻量单体优先
当前阶段以后端单体服务为主，避免过早引入重型微服务和 MQ。

#### 原则二：核心链路优先
优先保障以下主链路打通：

- 首次进入
- 会话初始化
- WebSocket 聊天
- 知识答疑
- 规则解释
- 退款执行
- 工单兜底

#### 原则三：受控式 AI
模型负责理解与生成，不直接承担高风险业务决策。高风险决策由规则层与工具结果控制。

#### 原则四：状态可见
前端页面状态、会话状态、连接状态、补槽状态、工具状态都要可追踪。

#### 原则五：记忆外部化
历史信息不直接等于模型上下文。当前 prompt 只装载必要上下文，其他历史以摘要和检索方式按需使用。

#### 原则六：Demo 可交付 + 产品化可扩展
当前实现可简化，但接口协议、状态模型、模块分层尽量不做死。

### 2.4 本文档范围

本文档覆盖：

- 前端技术设计
- 后端技术设计
- WebSocket 设计
- LangChain 编排设计
- RAG 设计
- 规则设计
- Tool 调用设计
- 数据模型设计
- 状态机设计
- 记忆体系设计
- 协议设计
- 异常与容错设计

### 2.5 非本文档范围

以下内容不作为本期重点：

- 生产级账号体系
- 多租户平台能力
- 多渠道接入
- 人工客服工作台
- 复杂运营后台
- 大规模分布式弹性伸缩
- 高级权限系统
- 复杂审计系统

---

## 3. 需求理解与技术映射

### 3.1 匿名接入如何实现

产品要求用户无需注册，只在首次进入时输入用户名。 
技术上需要拆为两层：

1. 前端本地身份标识
 - 首次进入后在本地保存 anonymous_user_token
2. 后端匿名用户模型
 - 根据 token 或首次注册请求生成匿名用户记录

用户名并不等于正式账号，而是匿名用户的展示名和会话补充信息。

### 3.2 用户名采集如何承接身份初始化

用户名提交后并不是只做前端展示，而是作为后端初始化匿名用户的必要输入。 
因此该动作需要同时触发：

- 匿名用户创建/获取
- 本地 token 写入
- 会话初始化
- WebSocket 建连准备

### 3.3 会话初始化如何实现

产品要求用户名提交后自动初始化会话，技术上需要：

- 创建 session_id
- 初始化当前会话状态
- 准备首问消息
- 绑定 WebSocket 会话上下文

### 3.4 WebSocket 为何需要

产品要求：

- 机器人主动首问
- 实时消息收发
- 重连与状态同步
- 处理中和结果消息及时推送

因此 WebSocket 比纯轮询更适合当前场景。 
对 Demo 阶段而言，WebSocket 能以较低实现成本提供接近真实 IM 的体验。

### 3.5 聊天式自然交互如何转化为技术流程

技术上不能把交互设计成一组表单字段提交，而应设计成：

- 用户自然输入
- 后端消息入链
- LangChain 进行结构化理解
- 判断是否补槽
- 选择知识 / 解释 / 工具链路
- 生成回复消息

### 3.6 问题与诉求联合识别如何落地

技术上通过一次模型调用输出结构化结果，例如：

- 当前问题类型
- 用户诉求类型
- 是否包含订单号
- 是否需要补槽
- 当前推荐链路

而不是拆成多个模型步骤逐次问答。

### 3.7 补槽追问如何实现

补槽不是前端表单，而是会话状态中的"待补字段"。 
系统需要维护：

- 当前主链路
- 当前缺失槽位
- 当前是否处于 follow-up 状态

用户补充后继续进入同一链路。

### 3.8 退款咨询与退款执行如何区分

技术上需由编排层进行判定：

- "能不能退 / 怎么退 / 多久到" → 咨询
- "帮我退款 / 申请退款" → 执行
- "为什么不能退" → 解释

该判定不可仅靠关键词粗暴路由，需模型结构化识别 + 规则约束。

### 3.9 纯知识答疑与规则解释答疑如何区分

- 纯知识答疑：仅依赖知识库
- 规则解释答疑：需知识 + 当前订单 / 工具状态

技术上这两条链路分别对应：

- RAG Answer Chain
- RAG + Context Explain Chain

### 3.10 工具调用与规则判断如何协同

Tool 不直接暴露给模型自由调用。 
正确流程应为：

1. 模型输出"建议执行退款"
2. 编排层判断是否为执行型意图
3. 校验订单号与必要参数
4. 规则层判断是否允许调用
5. Tool 代理层调用真实或模拟退款工具
6. 结果映射为前端卡片消息

### 3.11 工单兜底如何接入

工单兜底并不是异常页，而是会话中的一条可操作卡片消息。 
技术上需要：

- 生成工单摘要
- 形成工单提交请求
- 返回工单卡片消息
- 支持提交成功态替换

### 3.12 重复进线与记忆问题如何解决

产品虽然是 Demo，但已具备以下真实复杂性：

- 同一用户会重复咨询
- 同一订单会被多次追问
- 多轮对话会越来越长
- 当前主题会从咨询漂移到执行或工单

因此技术上必须引入轻量记忆体系来解决：

- 不同用户与不同订单的上下文隔离
- 超长上下文压缩
- 历史摘要检索
- 意图漂移控制

---

## 4. 总体架构设计

### 4.1 总体架构图（文字化描述）

整体架构可描述为：

H5 Vue 前端 
→ 通过 HTTP 完成匿名初始化 / 工单提交等基础请求 
→ 通过 WebSocket 与 FastAPI 后端 建立实时会话连接 
→ 后端将用户消息交给 对话编排层 
→ 编排层先读取 工作记忆（Working Memory） 并进行漂移判断 
→ 需要时触发 历史摘要检索（Memory Retrieval） 
→ 调用 LangChain 理解链路 
→ 根据结构化结果分流到：

- RAG 检索层
- 规则判断层
- Tool 调用层
- 工单兜底层

→ 结果统一封装为机器人消息协议 
→ WebSocket 推送回前端 
→ 前端根据消息类型渲染文本、追问、结果卡片、工单卡片等不同 UI 组件

### 4.2 架构分层

#### 4.2.1 表现层
- Vue 3 H5 页面
- 聊天主页面
- 状态条、弹窗、输入区、消息流、卡片组件

#### 4.2.2 接入与实时通信层
- HTTP 接口
- WebSocket 接入
- 连接管理
- 心跳与重连协议

#### 4.2.3 会话与消息层
- 匿名用户状态
- 会话管理
- 消息收发与持久化
- 会话恢复

#### 4.2.4 记忆管理层
- 工作记忆
- 会话摘要
- 主题记忆
- 用户长期记忆
- 历史检索

#### 4.2.5 对话编排层
- 用户消息统一入口
- 当前链路判定
- 补槽判断
- 漂移控制
- 调用 AI / RAG / 规则 / Tool

#### 4.2.6 AI 理解层
- LangChain Prompt 编排
- 结构化意图识别
- 实体抽取
- 诉求识别
- 回复润色

#### 4.2.7 RAG 检索层
- 知识文档向量化
- 检索
- 召回结果组织

#### 4.2.8 规则判断层
- 是否需订单号
- 是否可执行 Tool
- 是否该兜底工单

#### 4.2.9 Tool 调用层
- 退款 Tool 代理
- 统一结果模型
- 超时与失败处理

#### 4.2.10 工单兜底层
- 摘要生成
- 工单提交
- 成功 / 失败处理

#### 4.2.11 存储层
- SQLite / MySQL
- Redis（可选）
- 本地向量库（FAISS / Chroma）

### 4.3 模块职责与边界

| 模块 | 职责 | 输入 | 输出 | 边界说明 |
|---|---|---|---|---|
| 前端 H5 | 页面展示与交互 | 协议消息 | UI 状态 | 不做业务判断 |
| WebSocket 层 | 实时收发消息 | 消息对象 | 入站/出站事件 | 不做编排逻辑 |
| 会话服务 | 会话状态维护 | user/session/message | session context | 不直接调用模型 |
| 记忆服务 | 上下文隔离、摘要、检索 | session/topic/user | memory context | 不做最终业务决策 |
| 编排服务 | 主流程决策 | 用户消息 + session | reply plan | 核心编排中枢 |
| LangChain 服务 | 结构化理解与生成 | prompt/context | structured result / final text | 不做直接工具鉴权 |
| RAG 服务 | 知识检索 | query | docs/snippets | 不做最终路由 |
| 规则服务 | 业务约束判断 | current context | rule decision | 高风险动作前置 |
| Tool 服务 | 调用退款工具 | validated params | tool result | 不负责前端展示 |
| 工单服务 | 提交兜底工单 | ticket summary | submit result | 不直接生成对话 |

---

## 5. 核心技术链路设计

### 5.1 首次进入与身份初始化链路

#### 5.1.1 技术目标
完成匿名用户最小化初始化，并为后续会话建立基础身份。

#### 5.1.2 链路步骤
1. 前端加载 H5 页面。 
2. 检查本地是否存在 `anonymous_user_token`。 
3. 若不存在，则展示用户名弹窗。 
4. 用户提交用户名后，调用 HTTP 接口 `/api/v1/user/init-anonymous`。 
5. 后端生成匿名用户记录： 
 - anonymous_user_id 
 - anonymous_user_token 
 - username 
6. 前端将 token 持久化到 localStorage。 
7. 前端调用 /api/v1/session/init 创建新会话。 
8. 后端初始化 `session_memory`。 
9. 前端以 anonymous_user_token + session_id 发起 WebSocket 建连。 

#### 5.1.3 匿名用户 ID 生成建议
Demo 阶段建议使用：

- uuid4() 生成 anonymous_user_id
- 再生成独立 anonymous_user_token

#### 5.1.4 本地存储建议
前端 localStorage 保存：

- anonymous_user_token
- anonymous_user_id
- username
- latest_session_id

#### 5.1.5 异常处理
- 用户名非法：HTTP 直接返回校验错误
- 匿名初始化失败：前端停留弹窗态
- 会话初始化失败：前端转初始化失败提示态

### 5.2 WebSocket 建连与消息通信链路

#### 5.2.1 技术目标
提供低延迟、可恢复的实时聊天体验。

#### 5.2.2 技术选型
- FastAPI WebSocket 原生支持
- 前端使用原生 WebSocket 封装

#### 5.2.3 建连时机
- 会话初始化成功后立即建连
- 非首次访问恢复时，在页面初始化阶段建连

#### 5.2.4 建连方式建议
前端连接地址示例：

```
ws://host/ws/chat?token={anonymous_user_token}&session_id={session_id}
```

后端建连时进行：
- token 校验
- session_id 校验
- user-session 绑定

#### 5.2.5 心跳机制
Demo 阶段建议：
- 客户端每 20s 发送一次 ping
- 服务端返回 pong
- 连续 2 个周期失败视为断连

#### 5.2.6 消息 ack 机制
Demo 阶段建议采用轻量 ack：
- 客户端发消息时带 message_id
- 服务端收到后回一个 ack 消息
- 前端将用户消息状态从 sending 更新为 sent

#### 5.2.7 重连机制
前端重连策略：
- 断连后 1s / 2s / 5s 指数退避重连
- 最多 3 次
- 失败后进入"重连失败态"

#### 5.2.8 会话恢复
重连成功后：
- 前端带最新 session_id
- 服务端重新绑定上下文
- 服务端根据 session_memory 和持久化消息恢复当前会话状态
- 前端可调用 HTTP 接口拉取最近消息快照

### 5.3 首问触发链路

#### 5.3.1 设计原则
首问由服务端统一下发，而不是前端硬编码。

#### 5.3.2 触发时机
- WebSocket 建连成功后
- 当前会话消息为空时
- 服务端推送首条 bot_greeting

#### 5.3.3 失败处理
若首问下发失败：
- 前端仍可进入可输入态
- 服务端记录日志
- 可降级为前端本地展示默认欢迎文案（仅 Demo 兜底）

### 5.4 用户消息处理链路

#### 5.4.1 技术步骤
1. 前端通过 WebSocket 发送用户消息。 
2. 后端接收消息并做协议解析。 
3. 消息先写入消息表。 
4. 编排服务根据当前会话状态加载 Working Memory。 
5. 判断是否需要上下文压缩。 
6. 判断是否发生 topic/task 漂移。 
7. 必要时触发历史记忆检索。 
8. 进入 LangChain 结构化理解链路。 
9. 得到： 
 - 主意图 
 - topic 
 - task 
 - 诉求 
 - 槽位 
 - 是否需补槽 
 - 推荐处理链路 
10. 编排服务按结果路由： 
 - 知识答疑 
 - 规则解释 
 - 工具执行 
 - 兜底工单 
11. 生成一个或多个机器人消息对象。 
12. 写入消息表。 
13. 更新 Working Memory。 
14. WebSocket 推送给前端。 

#### 5.4.2 消息入站结构建议

```json
{
 "type": "user_message",
 "message_id": "msg_xxx",
 "session_id": "sess_xxx",
 "trace_id": "trace_xxx",
 "content": "帮我退款",
 "timestamp": 1710000000
}
```

#### 5.4.3 关键技术点
- 入站消息先持久化，再做编排
- 编排过程使用当前 session 上下文
- 机器人可返回多条消息，例如：
 - 一条解释消息
 - 一张结果卡片消息

### 5.5 补槽追问链路

#### 5.5.1 技术目标
在不打断自然对话体验的前提下补齐关键业务信息。

#### 5.5.2 实现策略
编排服务维护 `slot_state`，包括：
- 当前缺失槽位列表
- 当前待补主要槽位
- 当前 follow-up 原因

当 LangChain 识别出当前链路缺关键槽位时：
- 不进入最终业务处理
- 直接返回追问消息
- 同时更新 session 的槽位状态

#### 5.5.3 数据结构建议

```json
{
 "required_slots": ["order_id"],
 "filled_slots": {
 "issue_type": "refund_execute"
 },
 "pending_slot": "order_id",
 "followup_reason": "refund_execute_requires_order_id"
}
```

#### 5.5.4 用户补充后的处理
下一条用户消息到达时：
- 编排层先判断当前会话是否存在 pending_slot
- 若有，则优先尝试把该消息解释为槽位补充
- 成功后继续原链路，不重新从零开始

### 5.6 知识答疑链路

#### 5.6.1 技术目标
支持纯知识类问题的客服化回答。

#### 5.6.2 Demo 技术选型
建议：
- LangChain + Chroma 或 FAISS
- 文本切片后做向量索引
- 检索结果喂给 LLM 生成客服化答案

选型建议：Demo 阶段更推荐 **Chroma**。

#### 5.6.3 知识处理流程
1. 识别用户为纯知识答疑。 
2. 构造检索 query。 
3. 调用向量库检索 top-k。 
4. 将召回片段注入 Prompt。 
5. 生成客服化回答。 
6. 输出 bot_knowledge 消息。 

#### 5.6.4 无结果兜底
若检索分数低于阈值：
- 优先走追问缩小范围
- 否则给保守解释
- 必要时输出工单卡片

### 5.7 规则解释链路

#### 5.7.1 技术目标
回答"为什么当前不能退款/为什么失败"这类需要状态解释的问题。

#### 5.7.2 技术流程
1. 识别为解释型意图。 
2. 判断是否需要订单号。 
3. 若缺失则补槽追问。 
4. 若具备上下文： 
 - 查询规则知识片段 
 - 查询 topic_memory / tool_record 获取当前业务状态 
5. 构造 Explain Prompt。 
6. 输出解释型消息。 

#### 5.7.3 关键区别
该链路与纯知识答疑的区别在于：
- 多了业务上下文
- 多了历史订单主题记忆
- 输出不只是规则，而是"当前原因说明"

### 5.8 退款执行链路

#### 5.8.1 技术目标
在满足条件时发起退款申请，并把结果以卡片方式返回。

#### 5.8.2 技术流程
1. 识别为退款执行意图。 
2. 判断是否具备订单号。 
3. 若缺失则追问。 
4. 订单号齐全后走规则校验： 
 - 订单是否存在 
 - 是否允许退款 
 - 是否重复申请 
5. 通过后调用 Tool。 
6. 获取 Tool 返回。 
7. 统一转换为前端卡片消息。 
8. 同时写入 topic_memory / tool_record。 

#### 5.8.3 Tool 调用前防重
Demo 阶段建议使用：
- session_id + order_id + action_type 作为幂等键
- 短时间内重复请求直接拦截或提示处理中

### 5.9 工单兜底链路

#### 5.9.1 技术目标
在无法直接闭环时提供后续处理路径。

#### 5.9.2 技术流程
1. 编排服务判断需兜底。 
2. 生成工单摘要： 
 - 用户名 
 - 会话摘要 
 - 最近问题 
 - 订单号（如有） 
3. 返回一条工单卡片消息。 
4. 用户点击提交后： 
 - 通过 HTTP 或 WebSocket 指令提交工单 
 - 返回工单成功态消息 
5. 写入 ticket 表，并更新主题记忆中的未解决状态。 

Demo 取舍：本期可以采用轻量工单服务：
- 写入数据库 ticket 表
- 不必接入真实客服工单平台

---

## 6. 前端技术设计

### 6.1 技术选型

- Vue 3
- TypeScript
- Vite
- Pinia
- 原生 WebSocket 封装
- 移动端 H5 适配

### 6.2 前端分层设计

#### 6.2.1 页面容器层
负责：
- 页面初始化
- 匿名身份检查
- 会话初始化
- 路由承载

#### 6.2.2 聊天主容器层
负责：
- 消息流状态
- 聊天页面状态切换
- 首问展示
- 输入区联动

#### 6.2.3 消息渲染层
按消息类型组件化：
- 文本消息组件
- 追问消息组件
- 知识答疑消息组件
- 解释消息组件
- 结果卡片组件
- 工单卡片组件
- 系统状态消息组件

#### 6.2.4 输入交互层
负责：
- 输入框
- 发送按钮
- Enter 发送
- 发送态 / 禁用态

#### 6.2.5 状态提示层
负责：
- 顶部状态条
- 初始化中遮罩
- 重连中 / 重连失败提示

### 6.3 Pinia 状态管理建议

建议 store 划分：

#### useUserStore
- anonymousUserId
- anonymousToken
- username

#### useSessionStore
- sessionId
- sessionStatus
- connectionStatus
- pendingSlot
- currentFlow
- currentTopic
- currentTask

#### useChatStore
- messageList
- inputText
- isBotProcessing
- quickQuestionVisible

### 6.4 WebSocket 客户端封装建议

创建 `chatSocket.ts`：

- connect(sessionId, token)
- sendMessage(payload)
- close()
- reconnect()
- onMessage(handler)
- onOpen(handler)
- onClose(handler)
- onError(handler)

### 6.5 消息流渲染方案

前端统一基于 message.type 渲染组件：

```typescript
type MessageType =
 | "bot_greeting"
 | "user_text"
 | "bot_text"
 | "bot_followup"
 | "bot_knowledge"
 | "bot_explain"
 | "tool_result_card"
 | "ticket_card"
 | "system_status"
 | "error_message";
```

### 6.6 自动滚动策略
- 正常新消息到达自动滚到底部
- 若用户主动上滑查看历史，则暂不抢滚动
- 输入区键盘弹起时重新计算消息区高度

### 6.7 H5 键盘适配
- iOS / Android 分开验证
- 输入区 fixed 定位
- 留安全区 padding-bottom
- 键盘弹起时消息流容器高度动态调整

---

## 7. 后端技术设计

### 7.1 技术选型

- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy
- SQLite（Demo 默认）
- Redis（可选，当前阶段可不强依赖）
- LangChain
- Chroma（推荐）或 FAISS

### 7.2 后端模块划分

```
app/
├── api/
│   ├── http_routes.py
│   └── ws_routes.py
├── core/
│   ├── config.py
│   ├── logger.py
│   └── tracing.py
├── models/
│   ├── user.py
│   ├── session.py
│   ├── message.py
│   ├── slot.py
│   ├── ticket.py
│   ├── tool_record.py
│   ├── session_summary.py
│   ├── topic_memory.py
│   └── user_profile_memory.py
├── schemas/
│   ├── user_schema.py
│   ├── ws_schema.py
│   ├── message_schema.py
│   └── ticket_schema.py
├── services/
│   ├── user_service.py
│   ├── session_service.py
│   ├── message_service.py
│   ├── memory_service.py
│   ├── orchestrator_service.py
│   ├── rag_service.py
│   ├── rule_service.py
│   ├── tool_service.py
│   ├── ticket_service.py
│   └── llm_service.py
├── chains/
│   ├── intent_chain.py
│   ├── answer_chain.py
│   ├── explain_chain.py
│   └── summary_chain.py
├── repositories/
│   ├── user_repo.py
│   ├── session_repo.py
│   ├── message_repo.py
│   ├── ticket_repo.py
│   └── memory_repo.py
└── vectorstore/
    └── chroma_store.py
```

### 7.3 服务职责说明

#### user_service
- 匿名用户初始化
- 用户名校验
- 用户查询

#### session_service
- 会话创建
- 会话状态更新
- pending_slot 管理
- 当前 flow 管理

#### message_service
- 消息入库
- 消息查询
- 消息协议封装

#### memory_service
- Working Memory 加载与更新
- Session Summary 生成
- Topic Memory 更新
- User Profile 更新
- 历史摘要检索
- 漂移判断辅助

#### orchestrator_service
- 核心编排入口
- 调用 memory_service / intent_chain / rag_service / rule_service / tool_service
- 统一生成 reply plan

#### rag_service
- 文档加载
- 检索
- 检索结果返回

#### rule_service
- 规则判断
- 是否追问订单号
- 是否允许调用工具
- 是否触发工单

#### tool_service
- 退款 tool 代理调用
- 幂等控制
- 结果标准化

#### ticket_service
- 工单摘要生成
- 工单入库

#### llm_service
- 模型统一封装
- Prompt 调用
- 结构化输出解析

---

## 8. LangChain 与对话编排设计

### 8.1 LangChain 角色定位

LangChain 在本系统中承担以下职责：

1. 意图识别与槽位提取
2. 知识答疑链路编排
3. 规则解释链路编排
4. Tool 调用前的结构化理解
5. 客服化语言润色
6. 会话摘要生成

LangChain 不直接负责：
- 业务资格最终判断
- Tool 权限判定
- 会话持久化
- 状态机管理

### 8.2 编排方式建议

优先采用：
- PromptTemplate
- RunnableSequence
- RunnableLambda
- StructuredOutputParser 或模型原生 JSON 输出

### 8.3 意图识别链路

#### 输入
- 当前用户消息
- 最近 3~5 轮上下文
- 当前 session 状态
- 当前 pending_slot
- 历史摘要上下文（如需要）

#### 输出结构建议

```json
{
 "main_intent": "refund_execute",
 "topic": "refund",
 "task": "execute",
 "user_goal": "apply_refund",
 "issue_desc": "不想要了",
 "order_id": null,
 "need_followup": true,
 "missing_slots": ["order_id"],
 "recommended_flow": "tool",
 "is_topic_shift": false,
 "is_task_shift": true,
 "shift_reason": "user changed from consult to execute",
 "confidence": 0.92
}
```

### 8.4 Answer Chain 设计
用于纯知识问答：

- 输入：question + retrieved_docs
- 输出：客服化回答文本

### 8.5 Explain Chain 设计
用于规则解释：

- 输入：question + business_context + retrieved_rule_docs + memory_context
- 输出：解释型文本

### 8.6 Tool Calling 设计
Demo 阶段不建议完全放给模型自由 tool calling。 
建议方式：

- 模型给出 recommended_flow = tool
- 编排层根据规则决定是否真正调用 tool_service

### 8.7 保守回复策略
当模型不确定时：
- 不直接给高风险结论
- 优先补槽追问
- 再选择工单兜底

---

## 9. 知识库与 RAG 设计

### 9.1 知识来源
本期知识范围建议控制在：

- 运费规则
- 发货规则
- 售后规则
- 退款到账时效
- 售后说明
- 常见订单 / 物流说明

### 9.2 文档切分策略
建议：

- chunk size 300~500 中文字符
- overlap 50~80

### 9.3 向量库方案
推荐 Chroma：

- 本地化部署简单
- 适合 Demo
- 与 LangChain 集成方便

### 9.4 检索流程
1. 用户问题进入知识链路 
2. 生成 query 
3. 召回 top-k=3~5 
4. 若相似度不足则判为低命中 
5. 高命中则注入 Prompt 

### 9.5 无命中策略
- 优先追问
- 再保守解释
- 最后工单兜底

---

## 10. 规则判断设计

### 10.1 为什么需要规则层
模型擅长理解，但不应直接决定以下高风险动作：

- 是否执行退款
- 是否已满足订单条件
- 是否需要工单兜底

### 10.2 当前阶段规则实现建议
Demo 阶段推荐使用 **Python 代码规则 + 少量 JSON 配置**。

### 10.3 示例规则

#### 是否必填订单号
- 售前问题：否
- 退款执行：是
- 规则解释（个单相关）：是

#### 是否触发 Tool
必须同时满足：

- main_intent = refund_execute
- order_id != null
- 规则层判断通过

#### 是否触发工单
- 连续补槽失败
- 模型 / 检索 / 工具失败
- 用户继续坚持

---

## 11. Tool 调用设计

### 11.1 Tool 封装方式
在 LangChain 层不直接暴露底层退款接口。 
建议：

- 编排层调用 tool_service.apply_refund()

### 11.2 Tool 输入模型

```python
class RefundToolRequest(BaseModel):
 session_id: str
 anonymous_user_id: str
 order_id: str
 reason: str | None = None
 request_id: str
```

### 11.3 Tool 输出模型

```python
class RefundToolResult(BaseModel):
 status: Literal["success", "not_allowed", "need_more_info", "fail"]
 code: str
 message: str
 detail: dict | None = None
```

### 11.4 幂等策略
使用：

- idempotency_key = session_id + order_id + "refund"

### 11.5 前端卡片映射
Tool 结果统一映射为：

- success → 成功卡片
- not_allowed → 不可执行卡片
- fail → 失败卡片
- need_more_info → 追问或参数不足卡片

---

## 12. 数据模型设计

### 12.1 匿名用户模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| anonymous_token | string | 本地识别 token |
| username | string | 展示名 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 12.2 会话模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | session_id |
| anonymous_user_id | string | 关联用户 |
| status | string | active/closed/error |
| current_flow | string | chat/followup/knowledge/explain/tool/ticket |
| current_topic | string | refund/logistics/presale 等 |
| current_task | string | consult/explain/execute/followup/ticket |
| pending_slot | string | 当前待补槽位 |
| context_snapshot | text/json | 当前上下文摘要 |
| created_at | datetime | 创建时间 |

### 12.3 消息模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | message_id |
| session_id | string | 关联会话 |
| role | string | user/bot/system |
| type | string | 消息类型 |
| content | text | 文本内容 |
| payload | json | 卡片等扩展数据 |
| status | string | sending/sent/fail |
| trace_id | string | 链路追踪 |
| created_at | datetime | 创建时间 |

### 12.4 槽位模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| session_id | string | 所属会话 |
| slot_name | string | 槽位名 |
| slot_value | string | 槽位值 |
| status | string | filled/pending |
| source | string | model/user/rule |

### 12.5 Tool 调用记录模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| session_id | string | 会话 |
| tool_name | string | refund |
| request_payload | json | 请求参数 |
| result_status | string | success/not_allowed/fail |
| result_payload | json | 结果 |
| created_at | datetime | 时间 |

### 12.6 工单模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | ticket_id |
| session_id | string | 会话 |
| anonymous_user_id | string | 用户 |
| summary | text | 工单摘要 |
| status | string | created/failed |
| created_at | datetime | 时间 |

### 12.7 会话摘要模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| session_id | string | 会话 ID |
| anonymous_user_id | string | 用户 ID |
| topic | string | 主题 |
| task | string | 最终任务 |
| order_id | string | 订单号，可空 |
| summary | text | 会话摘要 |
| resolved | bool | 是否闭环 |
| next_action | string | 下一步动作 |
| created_at | datetime | 创建时间 |

### 12.8 主题记忆模型

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| anonymous_user_id | string | 用户 ID |
| topic_key | string | user + order 组合键 |
| topic | string | 主题 |
| order_id | string | 订单号 |
| latest_status | string | 最近状态 |
| latest_summary | text | 最近摘要 |
| unresolved_flag | bool | 是否未解决 |
| updated_at | datetime | 更新时间 |

### 12.9 用户长期记忆模型

| 字段 | 类型 | 说明 |
|---|---|---|
| anonymous_user_id | string | 用户 ID |
| frequent_topics | json | 高频主题 |
| last_open_ticket_flag | bool | 是否有未完成工单 |
| preference_profile | json | 偏好信息 |
| updated_at | datetime | 更新时间 |

---

## 13. 状态机设计

### 13.1 用户状态机
- uninitialized
- anonymous_ready

### 13.2 会话状态机
- creating
- active
- closed
- error

### 13.3 WebSocket 状态机
- connecting
- connected
- reconnecting
- disconnected

### 13.4 对话轮次状态机
- received
- understanding
- waiting_followup
- answering
- tool_processing
- completed
- fallback

### 13.5 槽位状态机
- empty
- pending
- filled

### 13.6 Tool 状态机
- ready
- checking
- calling
- success
- not_allowed
- fail

### 13.7 工单状态机
- suggested
- submitting
- created
- failed

### 13.8 Topic / Task 状态机
- topic: refund / logistics / aftersale / presale / unknown
- task: consult / explain / execute / followup / ticket

流转原则：
- 同主题内任务切换视为弱漂移
- 切换到新主题视为强漂移
- 强漂移时触发旧上下文压缩归档

---

## 14. 接口与协议设计

### 14.1 HTTP 接口建议

#### 匿名用户初始化
POST /api/v1/user/init-anonymous

#### 会话初始化
POST /api/v1/session/init

#### 获取最近消息
GET /api/v1/session/{session_id}/messages

#### 提交工单
POST /api/v1/ticket/create

### 14.2 WebSocket 入站协议

```json
{
 "type": "user_message",
 "message_id": "msg_xxx",
 "session_id": "sess_xxx",
 "trace_id": "trace_xxx",
 "content": "帮我退款",
 "timestamp": 1710000000
}
```

### 14.3 WebSocket 出站协议

```json
{
 "type": "bot_message",
 "message_id": "msg_bot_xxx",
 "session_id": "sess_xxx",
 "trace_id": "trace_xxx",
 "payload": {
 "message_type": "tool_result_card",
 "content": "当前暂不支持退款",
 "card": {
 "title": "当前暂不支持退款",
 "description": "该订单当前不满足退款条件",
 "actions": [
 { "label": "提交跟进请求", "action": "create_ticket" },
 { "label": "继续了解原因", "action": "ask_more" }
 ]
 }
 }
}
```

### 14.4 通用字段建议
- trace_id
- message_id
- session_id
- timestamp

---

## 15. 存储与缓存设计

### 15.1 Demo 存储建议
优先使用：

- SQLite：结构化数据存储
- Chroma：向量索引
- Redis：可选，不强制

### 15.2 SQLite 存储内容
- 匿名用户
- 会话
- 消息
- 工单
- Tool 调用记录
- 槽位记录
- session_summary
- topic_memory
- user_profile_memory

### 15.3 Redis（可选）用途
若引入 Redis，可用于：

- WebSocket session 映射
- 短期会话上下文缓存
- 幂等键缓存
- Working Memory 外部化

但当前 Demo 阶段不是必须。

---

## 16. 异常与容错设计

### 16.1 用户名校验失败
- 后端返回 400
- 前端保留弹窗报错

### 16.2 会话初始化失败
- 前端显示初始化失败提示
- 允许手动重试

### 16.3 WebSocket 建连失败
- 页面进入重连中
- 失败后展示重试按钮

### 16.4 WebSocket 中断
- 顶部状态条提示
- 自动退避重连
- 恢复后重新进入 connected

### 16.5 模型调用失败
- 记录日志
- 返回保守回复
- 必要时工单兜底

### 16.6 知识检索无结果
- 优先追问
- 再保守解释
- 最后工单兜底

### 16.7 Tool 调用失败
- 区分系统异常和业务不满足
- 系统异常走失败卡片
- 业务不满足走解释卡片

### 16.8 工单提交失败
- 前端提示"提交未完成"
- 提供重试入口

### 16.9 记忆读取失败
- 当前轮降级为仅使用最近消息
- 不中断主链路
- 记录 warning 日志

### 16.10 压缩失败
- 保留最近窗口消息
- 不阻断当前回复
- 异步记录失败日志

### 16.11 漂移误判
- 标记 topic_shift_suspected
- 下一轮继续观察
- 避免一次误判就强制切换主题

---

## 17. 安全设计

### 17.1 匿名身份安全
- 使用 token 作为匿名身份标识
- token 不暴露内部自增 ID
- token 采用随机 UUID

### 17.2 WebSocket 连接保护
- 连接需携带 token + session_id
- 服务端校验 session 是否属于当前 token

### 17.3 输入内容校验
- 用户名、订单号做格式校验
- 用户消息长度做上限控制

### 17.4 Prompt 注入控制
- RAG 上下文与用户输入分隔注入
- Prompt 中明确要求不得越权回答
- Tool 调用不直接交给模型自由执行

### 17.5 日志脱敏
- 订单号只打印部分
- token 不完整打印
- 用户原文可按需脱敏采样

---

## 18. 可观测性设计

### 18.1 日志设计
使用 Python logging，输出 JSON 风格日志，至少包含：

- trace_id
- session_id
- message_id
- module
- event
- status

### 18.2 Trace 设计
每次用户消息生成一个 `trace_id`，贯穿：

- WebSocket 入站
- Working Memory 读取
- 历史摘要检索
- 编排
- RAG
- Tool
- WebSocket 出站

### 18.3 核心指标
- 会话初始化成功率
- WebSocket 建连成功率
- 首问响应时延
- 意图识别链路成功率
- RAG 命中率
- Tool 成功率
- 工单兜底率
- 记忆检索命中率
- 上下文压缩触发次数
- 强漂移 / 弱漂移次数

---

## 19. 性能与非功能设计

### 19.1 时延目标
- 首问响应：< 2s
- 普通问答：< 3s
- Tool 处理提示出现：< 1s
- Tool 完整返回：建议 < 5s

### 19.2 可维护性
- 单体应用内部模块清晰
- 编排逻辑与 API 层分离
- Prompt 独立管理
- 记忆层接口独立，便于后续拆分

### 19.3 可扩展性
未来可逐步扩展为：

- Redis 会话缓存
- MySQL 持久化
- 独立 RAG 服务
- 独立 Tool 服务
- 配置化规则系统
- 独立 Memory Service

---

## 20. 技术选型与取舍说明

### 20.1 为什么选 FastAPI
- 轻量
- HTTP + WebSocket 支持好
- Python 生态与 LangChain 集成自然
- 适合 Demo 快速开发

### 20.2 为什么选 LangChain
- 能快速组织 LLM、Prompt、RAG、Tool
- 适合当前 AI 编排型 Demo
- 比纯手写 prompt orchestration 更易维护

### 20.3 为什么当前优先单体
- 当前目标是 Demo，不适合过度微服务
- 单体更有利于快速联调与演示
- 后续可以按模块拆分

### 20.4 为什么当前不强依赖 MQ
- 当前链路以同步响应为主
- 消息规模小
- 引入 MQ 会增加系统复杂度
- 后续如接入真实工单、异步通知再考虑

### 20.5 SQLite / MySQL 取舍
当前 Demo 推荐 SQLite：
- 部署最轻
- 无需额外 DB 服务
- 足够支撑演示

若团队已有现成 MySQL，也可直接上 MySQL 以减少后续迁移。

### 20.6 为什么当前只做轻量记忆体系
- 当前业务重点在流程闭环，不在复杂记忆系统
- 轻量 Working Memory + Summary + Topic Memory 就能覆盖 80% 问题
- 先跑通隔离、压缩、检索、漂移四件事，比一开始做重型 memory platform 更合理

---

## 21. 部署与环境设计

### 21.1 开发环境
- 本地前端 Vite dev server
- 本地 FastAPI 服务
- 本地 Chroma / 本地向量索引
- SQLite 文件库

### 21.2 测试环境
- 单实例 FastAPI
- 前端静态部署
- SQLite 或轻量 MySQL
- 文档和工具数据固定

### 21.3 Demo 环境
建议 Docker 化：

- 前端 nginx 静态服务
- FastAPI 服务
- SQLite 文件挂载
- 本地向量索引目录挂载

---

## 22. 研发拆分建议

### 22.1 前端任务
- 聊天主页面
- 用户名弹窗
- WebSocket 客户端
- 消息组件渲染
- 状态条与异常态
- 工具结果卡片
- 工单卡片

### 22.2 后端任务
- 匿名用户与会话接口
- WebSocket 接入
- 消息服务
- 编排服务
- RAG 服务
- Tool 服务
- 工单服务
- 记忆服务

### 22.3 AI 任务
- Prompt 设计
- LangChain 编排
- 结构化输出设计
- 知识向量化
- 解释链路设计
- 摘要链路设计

### 22.4 测试任务
- 页面状态联调
- 补槽链路
- 知识链路
- Tool 三态
- 重连恢复
- 工单提交
- 历史咨询承接
- 意图漂移场景

---

## 23. 记忆体系设计

> 本章用于解决以下关键问题： 
> 1. 不同用户 / 相同用户不同订单的上下文隔离 
> 2. 长对话导致的上下文溢出 
> 3. 重复进线咨询时的历史对话压缩与检索 
> 4. 多轮对话中的意图漂移控制 

### 23.1 设计目标

记忆体系需要同时满足以下目标：

1. 会话内连续性 
 - 支撑当前会话中的多轮追问、补槽、解释与工具调用。 
2. 跨会话可恢复 
 - 支撑重复进线咨询、历史问题回溯、未完成事项延续。 
3. 上下文可控 
 - 控制送入大模型的上下文大小，避免 prompt 溢出。 
4. 上下文隔离 
 - 不同用户、不同订单、不同问题主题之间不串线。 
5. 主题可切换 
 - 在意图漂移场景下能平滑切换上下文，不让历史上下文污染当前问题。 
6. Demo 可实现 
 - 当前阶段优先采用轻量内存对象 + SQLite/MySQL 持久化 + 向量检索的组合方式。 

### 23.2 设计原则

#### 原则一：记忆外部化
历史信息不等于模型上下文。 
模型上下文只保留当前任务真正需要的最小信息，其他历史信息沉淀在外部记忆层中，按需检索。

#### 原则二：分层记忆
不同时间尺度、不同业务粒度的信息进入不同记忆层，不把所有内容混在一起。

#### 原则三：强隔离
记忆必须按用户、会话、订单、工单等维度进行隔离，避免历史污染。

#### 原则四：可压缩
对长对话必须支持自动摘要和窗口裁剪，不能无限累积。

#### 原则五：可检索
跨会话记忆必须支持结构化查询和相似检索，而不是无差别全量回放。

#### 原则六：主题可切换
会话中当前"主题（topic）"和"任务（task）"要分开管理，支持意图漂移时切换上下文。

### 23.3 记忆分层架构

#### 23.3.1 工作记忆（Working Memory）
用于当前会话、当前问题的即时处理。

保存内容：
- 最近 N 轮对话
- 当前主主题（topic）
- 当前任务（task）
- 当前待补槽位
- 当前订单号
- 当前工具调用状态
- 当前是否已进入工单兜底

特点：
- 生命周期短
- 存储在内存或 Redis（Demo 阶段可优先内存）
- 直接参与当前 Prompt 组装

#### 23.3.2 会话摘要记忆（Session Summary Memory）
用于压缩单次会话的核心信息。

保存内容：
- 会话主题摘要
- 用户主要诉求
- 关键订单号
- 最终处理结果
- 是否转工单
- 未解决问题

特点：
- 由会话结束时或超长会话压缩时生成
- 用于后续重复进线召回
- 不直接保存全量原文

#### 23.3.3 主题记忆（Topic Memory）
用于围绕某个业务对象（如订单）形成聚合记忆。

保存内容：
- order_id
- 当前主题（refund / logistics / aftersale）
- 最近处理状态
- 最近结论
- 最近未完成动作
- 最近工单状态
- 最后一次咨询时间

特点：
- 与订单、工单等业务对象绑定
- 比 session 记忆更稳定
- 用于同一订单重复咨询

#### 23.3.4 用户长期记忆（User Profile Memory）
用于记录用户跨会话的轻量偏好和高频模式。

保存内容建议：
- 常见咨询主题偏好
- 最近是否存在未完成工单
- 高频咨询类型
- 服务偏好（如是否偏好简洁回答）

#### 23.3.5 可检索历史记忆（Retrieval Memory）
用于跨会话、跨主题的历史检索。

数据来源：
- 会话摘要
- 订单主题摘要
- 工单摘要
- Tool 结果摘要

检索方式：
- 精确过滤：按 anonymous_user_id / order_id / topic / ticket_id
- 关键字检索
- 向量检索（Demo 可选）

### 23.4 上下文隔离设计

#### 23.4.1 隔离键设计

建议在系统中引入以下 4 类 key：

用户隔离键

```
user_scope_key = anonymous_user_id
```

会话隔离键

```
session_scope_key = session_id
```

业务对象隔离键

```
topic_scope_key = anonymous_user_id + order_id
```

工单隔离键

```
ticket_scope_key = ticket_id
```

#### 23.4.2 隔离规则

规则一：当前模型上下文只读当前会话工作记忆 
默认只从 session_scope_key 对应的 Working Memory 中取上下文。

规则二：跨会话历史默认不直接注入原始对话 
只能通过"摘要检索"方式召回。

规则三：有订单号时优先按订单隔离 
当当前链路识别出 order_id 后，检索和记忆优先绑定到 `topic_scope_key`。

规则四：用户级记忆不能直接当业务事实使用 
用户长期记忆只能做辅助偏好和历史趋势，不得直接作为当前订单状态结论。

#### 23.4.3 Demo 阶段建议实现
- `session_memory`：进程内内存字典或 Redis
- `session_summary`：SQLite/MySQL 表
- `topic_memory`：SQLite/MySQL 表
- `user_profile_memory`：SQLite/MySQL 表

Python 结构示例：

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class WorkingMemory:
 session_id: str
 anonymous_user_id: str
 current_topic: str = "unknown"
 current_task: str = "chat"
 pending_slot: Optional[str] = None
 current_order_id: Optional[str] = None
 recent_messages: List[dict] = field(default_factory=list)
 latest_summary: Optional[str] = None
 tool_status: Optional[str] = None
```

### 23.5 上下文窗口与压缩策略

#### 23.5.1 Prompt 组装原则
每次调用模型时，只允许注入以下内容：

1. 系统提示词
2. 当前用户最新消息
3. 最近 3~6 轮关键对话
4. 当前工作记忆摘要
5. 少量高相关历史摘要
6. 少量检索到的知识片段

#### 23.5.2 压缩触发条件
建议满足以下任一条件时触发压缩：

- 当前会话轮次 > 12 轮
- 最近对话消息估算 token > 6k
- 当前会话中已经发生主题切换
- 工具结果已明确，旧问题链路可归档

#### 23.5.3 压缩产物结构

```json
{
 "session_id": "sess_xxx",
 "summary": "用户咨询订单 10001 为何不能退款，已解释超过售后申请时效，用户暂未接受，建议提交工单。",
 "topic": "refund",
 "task": "explain",
 "resolved": false,
 "order_id": "10001",
 "next_action": "offer_ticket"
}
```

#### 23.5.4 压缩后保留策略
压缩后当前 Working Memory 只保留：

- 最近 2~4 轮原始消息
- 压缩摘要
- 当前 topic / task
- 当前 pending_slot
- 当前 order_id
- 当前 tool_status

### 23.6 重复进线咨询的历史对话压缩与查询

#### 23.6.1 历史信息沉淀策略
建议采用"三段式沉淀"：

A. 原始对话日志 
用于回放、排障、审计，不直接参与模型推理。

B. 会话摘要 
每次会话结束或压缩时生成，用于重复进线召回。

C. 业务对象摘要 
按 order_id 聚合，用于同一订单问题快速恢复。

#### 23.6.2 历史查询策略

场景一：用户再次进线但未提订单号 
优先查询：
- 最近 3 次 session_summary
- 最近未完成 ticket
- 最近高频 topic

场景二：用户提到订单号 
优先查询：
- topic_memory 中该 order_id
- 最近与该订单相关的 session_summary
- 最近 tool_record 摘要

场景三：用户继续未完成问题 
优先查询：
- status in (unresolved, ticket_pending) 的历史摘要

#### 23.6.3 历史检索注入规则
每次最多注入：
- 1 条用户级摘要
- 1~2 条订单级摘要
- 1 条未完成工单摘要

### 23.7 意图漂移设计

#### 23.7.1 Topic 与 Task 双层建模
建议不要只存一个 `current_intent`，而是拆成：
- `current_topic`：主题
- `current_task`：任务

主题示例
- refund
- logistics
- aftersale
- presale
- unknown

任务示例
- consult
- explain
- execute
- followup
- ticket

#### 23.7.2 意图漂移分类

弱漂移 
同一主题内任务变化，例如：
- refund_consult → refund_execute
- refund_explain → refund_ticket

处理方式：
- 保持 topic
- 更新 task
- 保留当前订单上下文

强漂移 
切换到全新主题，例如：
- refund → logistics
- logistics → presale

处理方式：
- 将旧 Working Memory 压缩
- 重建新的当前工作记忆
- 必要时提示用户当前是否切换问题

#### 23.7.3 模型结构化输出建议

```json
{
 "main_intent": "refund_execute",
 "topic": "refund",
 "task": "execute",
 "is_topic_shift": false,
 "is_task_shift": true,
 "shift_reason": "user changed from consult to execute",
 "need_followup": true,
 "missing_slots": ["order_id"]
}
```

#### 23.7.4 编排层处理策略
- 若 is_task_shift = true 且 `is_topic_shift = false`：
 - 更新当前 task
 - 不清空旧 topic 上下文
- 若 `is_topic_shift = true`：
 - 先压缩当前工作记忆
 - 初始化新主题工作记忆

### 23.8 记忆存储设计

#### 23.8.1 推荐表结构

session_summary 表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| session_id | string | 会话 ID |
| anonymous_user_id | string | 用户 ID |
| topic | string | 主题 |
| task | string | 最终任务 |
| order_id | string | 订单号，可空 |
| summary | text | 会话摘要 |
| resolved | bool | 是否闭环 |
| next_action | string | 下一步动作 |
| created_at | datetime | 创建时间 |

topic_memory 表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 主键 |
| anonymous_user_id | string | 用户 ID |
| topic_key | string | user + order 组合键 |
| topic | string | 主题 |
| order_id | string | 订单号 |
| latest_status | string | 最近状态 |
| latest_summary | text | 最近摘要 |
| unresolved_flag | bool | 是否未解决 |
| updated_at | datetime | 更新时间 |

user_profile_memory 表

| 字段 | 类型 | 说明 |
|---|---|---|
| anonymous_user_id | string | 用户 ID |
| frequent_topics | json | 高频主题 |
| last_open_ticket_flag | bool | 是否有未完成工单 |
| preference_profile | json | 偏好信息 |
| updated_at | datetime | 更新时间 |

### 23.9 检索与注入设计

#### 23.9.1 查询入口
当满足以下场景之一时触发 memory retrieval：

- 规则解释型问题
- 用户重复咨询相同订单
- 当前对话发生强漂移但疑似与历史相关
- 用户表达"上次说过""之前不是这样"

#### 23.9.2 检索流程
1. 根据当前 session 状态判断是否已有 order_id 
2. 若有，优先查 topic_memory 
3. 再查最近 session_summary 
4. 若需要，再查 user_profile_memory 
5. 召回结果做去重与排序 
6. 注入 Prompt 的 retrieved_memory_context 

#### 23.9.3 Prompt 注入格式建议

```
[历史摘要]
- 该用户曾在 2026-03-09 就订单 10001 咨询退款问题
- 上次结论：超过售后申请时效，暂不支持退款
- 上次建议：可提交工单继续核实
```

### 23.10 LangChain 编排接入方案

#### 23.10.1 编排链路建议

```
用户消息
-> Working Memory 读取
-> Context Budget Check
-> Drift Detect
-> 必要时 Memory Retrieval
-> LangChain Intent + Slot Chain
-> 规则判断
-> RAG / Explain / Tool / Ticket
-> Memory Update
-> 必要时 Summary 压缩落库
```

#### 23.10.2 建议新增编排步骤
- Working Memory Load
- Context Budget Check
- Drift Detect
- Memory Retrieve
- Intent + Slot Parse
- Action Route
- Memory Update

### 23.11 异常与容错设计

#### 23.11.1 记忆读取失败
- 当前轮降级为仅使用最近消息
- 不中断主链路
- 记录 warning 日志

#### 23.11.2 历史摘要缺失
- 不报错
- 按新会话处理
- 必要时弱化"上次咨询"能力

#### 23.11.3 压缩失败
- 不影响当前轮回复
- 仅保留最近窗口消息
- 后台记录异常

#### 23.11.4 漂移误判
- 保留 topic_shift_suspected 标记
- 下一轮继续观察
- 避免一次误判就彻底切走上下文

### 23.12 Demo 阶段与产品化阶段取舍

#### 23.12.1 Demo 阶段建议
- 不做独立 Memory Service
- 不做复杂用户画像系统
- 不做全量向量化历史消息
- 只做：
 - Working Memory
 - Session Summary
 - Topic Memory
 - 简单 SQL 检索
 - 必要时少量向量检索

#### 23.12.2 产品化阶段演进建议
后续可逐步升级为：
- Redis Working Memory
- MySQL / PostgreSQL 持久化
- 独立 Memory Retrieval Service
- 更细粒度订单 / 工单聚合记忆
- 用户长期偏好与未解决事项中心
- 向量检索 + 结构化过滤混合召回

### 23.13 推荐最小落地方案（当前 Demo）

建议当前就实现以下最小闭环：

必做
1. `session_memory`：当前会话工作记忆 
2. `session_summary`：会话结束或超长压缩摘要 
3. `topic_memory`：按订单聚合状态 
4. topic + task 双层意图状态 
5. pending_slot 明确存储 
6. 进入解释链路时优先查 topic_memory 

可后补
1. user_profile_memory 
2. 向量化历史摘要检索 
3. 更复杂的漂移确认策略 
4. 更精细的上下文预算器 

---

## 24. 技术风险与待确认事项

### 24.1 技术风险
- WebSocket 在弱网环境下的稳定性风险
- LangChain 结构化输出不稳定风险
- RAG 质量依赖知识准备质量
- Tool 模拟与真实业务规则可能不一致
- 单体状态管理需避免逻辑耦合过高
- 记忆检索不当可能导致错误历史污染当前问题
- 漂移误判可能导致上下文切换异常

### 24.2 待确认事项
1. 最终使用哪家模型服务。 
2. Demo 阶段退款 Tool 是真实调用还是 Mock。 
3. 工单是否接真实系统。 
4. SQLite 还是直接接 MySQL。 
5. 首批知识文档范围和格式。 
6. 订单号格式规则是否已确定。 
7. 是否在 Demo 阶段就引入 Redis 做 Working Memory。 
8. 重复进线演示场景是否需要真实历史召回能力。 

---

## 25. 结论

本方案基于 Demo 轻量化优先 原则，采用：

- 前端：Vue 3 + TypeScript + Pinia
- 后端：Python + FastAPI
- AI 编排：LangChain
- RAG：Chroma / FAISS 本地向量检索
- 存储：SQLite（可平滑升级 MySQL）
- 记忆体系：Working Memory + Session Summary + Topic Memory

以单体分层架构快速支撑：

- 匿名接入
- WebSocket 实时聊天
- AI 理解与补槽
- 知识答疑
- 规则解释
- 退款执行 Tool 调用
- 工单兜底
- 重复进线咨询的轻量历史承接
- 意图漂移下的上下文控制

该方案能够在较短周期内完成 Demo 落地，并为后续产品化保留清晰的架构演进路径。
