# E2E Testing

ServiceBrain 端到端测试使用 Playwright。

## 安装

```bash
cd e2e
npm install
npx playwright install
```

## 运行测试

```bash
# 运行所有测试
npm run test:e2e

# 带 UI 运行
npm run test:e2e:ui

# 调试模式
npm run test:e2e:debug

# 查看报告
npm run test:e2e:report
```

## 测试场景

1. **首次进入流程**
   - 用户名弹窗显示
   - 提交后进入聊天页面

2. **首问消息**
   - 机器人主动发送欢迎消息

3. **多轮对话 - 退款咨询**
   - 用户咨询退款规则
   - 机器人回复规则说明

4. **退款执行**
   - 用户申请退款
   - 追问订单号
   - 返回结果卡片

5. **规则解释**
   - 用户问为什么不能退款
   - 机器人解释原因

6. **工单兜底**
   - 连续模糊表达
   - 引导工单提交

## 测试数据

| 订单号前缀 | 预期结果 |
|---|---|
| 1xxxxxxx | 退款成功 |
| 2xxxxxxx | 不可退款（超时） |
| 3xxxxxxx | 系统失败 |

## 前置条件

1. 前端服务运行在 `http://localhost:5173`
2. 后端服务运行在 `http://localhost:8000`
3. WebSocket 连接可用

## CI/CD 集成

测试报告输出到 `e2e/playwright-report/`，可上传到 CI 系统。
