/**
 * ServiceBrain E2E 端到端测试
 * 
 * 测试场景：
 * 1. 首次进入 - 用户名弹窗
 * 2. 会话初始化 - 首问消息
 * 3. 多轮对话 - 退款咨询
 * 4. 退款执行 - 工具调用
 * 5. 规则解释 - 为什么不能退款
 * 6. 工单兜底 - 无法闭环场景
 */

import { test, expect } from '@playwright/test';

// 增加超时时间
test.setTimeout(60000);

// 测试数据
const TEST_USER = {
  username: `test_user_${Date.now()}`,
};

const TEST_ORDER_IDS = {
  success: '10000001',      // 以 1 开头 → 退款成功
  not_allowed: '20000001',  // 以 2 开头 → 不可退款
  fail: '30000001',         // 以 3 开头 → 系统失败
};

test.describe('ServiceBrain E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // 访问首页
    await page.goto('/');
  });

  test.describe('首次进入流程', () => {
    test('应该显示用户名弹窗', async ({ page }) => {
      // 等待用户名弹窗出现
      await expect(page.locator('input[placeholder*="王先生"], .username-input').first()).toBeVisible();
    });

    test('输入用户名后应该进入聊天页面', async ({ page }) => {
      // 输入用户名
      const usernameInput = page.locator('input[placeholder*="王先生"], .username-input').first();
      await usernameInput.fill(TEST_USER.username);
      
      // 点击提交按钮
      const submitButton = page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first();
      await submitButton.click();
      
      // 等待初始化完成
      await page.waitForTimeout(2000);
      
      // 应该看到输入框
      await expect(page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first()).toBeVisible();
    });
  });

  test.describe('首问消息', () => {
    test('应该收到机器人首问消息', async ({ page }) => {
      // 输入用户名并提交
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      
      // 等待首问消息
      await page.waitForTimeout(3000);
      
      // 应该看到欢迎消息
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.first()).toBeVisible();
      
      // 消息内容应该包含欢迎词
      const firstBotMessage = await botMessages.first().textContent();
      expect(firstBotMessage).toContain('你好');
    });
  });

  test.describe('多轮对话 - 退款咨询', () => {
    test('用户咨询退款规则，机器人应该回复规则说明', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      // 发送退款咨询消息
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      await inputBox.fill('退款多久到账');
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      
      // 等待回复
      await page.waitForTimeout(3000);
      
      // 应该看到机器人回复
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.last()).toBeVisible();
      
      // 回复应该包含退款相关信息
      const lastBotMessage = await botMessages.last().textContent();
      expect(lastBotMessage.length).toBeGreaterThan(0);
    });
  });

  test.describe('退款执行', () => {
    test('用户申请退款，提供订单号后应该收到结果卡片', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      // 发送退款申请
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      await inputBox.fill('帮我退款');
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      
      // 等待追问订单号
      await page.waitForTimeout(3000);
      
      // 发送订单号（成功场景）
      await inputBox.fill(TEST_ORDER_IDS.success);
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      
      // 等待处理结果
      await page.waitForTimeout(5000);
      
      // 应该看到结果卡片或回复
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.last()).toBeVisible();
    });

    test('订单号以 2 开头应该返回不可退款', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      // 发送退款申请
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      await inputBox.fill('帮我退款');
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      await page.waitForTimeout(3000);
      
      // 发送不可退款的订单号
      await inputBox.fill(TEST_ORDER_IDS.not_allowed);
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      await page.waitForTimeout(5000);
      
      // 应该看到不可退款的回复（卡片消息或文本）
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.last()).toBeVisible();
      
      const lastMessage = await botMessages.last().textContent();
      // 卡片消息标题或文本应包含"不支持"、"暂不"、"超过"等关键词
      expect(lastMessage).toMatch(/不支持|暂不|不可|不能|超过/i);
    });
  });

  test.describe('规则解释', () => {
    test('用户问为什么不能退款，机器人应该解释原因', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      // 发送解释型问题
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      await inputBox.fill('为什么不能退款');
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      
      // 等待回复
      await page.waitForTimeout(3000);
      
      // 应该看到解释型回复
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.last()).toBeVisible();
    });
  });

  test.describe('工单兜底', () => {
    test('连续模糊表达后应该引导工单', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      
      // 连续发送 3 条模糊消息
      const fuzzyMessages = ['有问题', '不行', '你帮我看看'];
      
      for (const msg of fuzzyMessages) {
        await inputBox.fill(msg);
        await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
        await page.waitForTimeout(2000);
      }
      
      // 应该看到工单引导或追问
      const botMessages = page.locator('.message-item.bot, .bot-message, [class*="bot"]');
      await expect(botMessages.last()).toBeVisible();
    });
  });

  test.describe('消息类型渲染', () => {
    test('用户消息应该显示在右侧', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      await page.waitForTimeout(2000);
      
      // 发送消息
      const inputBox = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"]').first();
      await inputBox.fill('测试消息');
      await page.locator('button:has-text("发送"), button[type="submit"]').last().click();
      await page.waitForTimeout(2000);
      
      // 用户消息应该在右侧
      const userMessages = page.locator('.message-item.user, .user-message, [class*="user"], [class*="right"]');
      await expect(userMessages.last()).toBeVisible();
    });
  });

  test.describe('WebSocket 连接', () => {
    test('应该建立 WebSocket 连接', async ({ page }) => {
      // 完成登录
      await page.locator('input[placeholder*="王先生"], .username-input').first().fill(TEST_USER.username);
      await page.locator('button:has-text("开始咨询"), button:has-text("开始"), button:has-text("咨询")').first().click();
      
      // 等待连接
      await page.waitForTimeout(2000);
      
      // 检查连接状态（如果有状态指示器）
      const statusIndicator = page.locator('[class*="status"], [class*="connected"], .status');
      if (await statusIndicator.count() > 0) {
        const statusText = await statusIndicator.first().textContent();
        expect(statusText.toLowerCase()).not.toContain('error');
      }
    });
  });
});
