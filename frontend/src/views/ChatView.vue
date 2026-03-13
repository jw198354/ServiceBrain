<template>
  <div class="chat-container">
    <!-- 顶部导航 -->
    <div class="header">
      <div class="title">智能客服助手</div>
    </div>

    <!-- 系统状态条 -->
    <div v-if="connectionStatus !== 'connected'" class="status-bar" :class="statusClass">
      {{ statusText }}
    </div>

    <!-- 消息流区域 -->
    <div class="message-list" ref="messageListRef">
      <div v-for="message in messages" :key="message.message_id" class="message-item" :class="message.sender">
        <div class="message-bubble">
          <template v-if="(message.payload?.message_type || message.type)?.includes('card')">
            <!-- 卡片消息 -->
            <div class="card" :class="message.payload?.card?.status || message.card?.status">
              <div class="card-title">{{ message.payload?.card?.title || message.card?.title }}</div>
              <div class="card-description">{{ message.payload?.card?.description || message.card?.description }}</div>
              <div v-if="message.payload?.card?.actions || message.card?.actions" class="card-actions">
                <button
                  v-for="action in (message.payload?.card?.actions || message.card?.actions)"
                  :key="action.label"
                  class="action-btn"
                  @click="handleCardAction(action)"
                >
                  {{ action.label }}
                </button>
              </div>
            </div>
          </template>
          <template v-else>
            <!-- 文本消息 -->
            <div class="text-content">{{ message.payload?.content || message.content }}</div>
          </template>
          <div class="message-time">{{ formatTime(message.timestamp) }}</div>
        </div>
      </div>
      
      <!-- 处理中提示 -->
      <div v-if="isBotProcessing" class="message-item bot">
        <div class="message-bubble processing">
          <span class="processing-dot">●</span>
          <span class="processing-dot">●</span>
          <span class="processing-dot">●</span>
        </div>
      </div>
    </div>

    <!-- 快捷问题区域 -->
    <div v-if="quickQuestionsVisible && messages.length <= 1" class="quick-questions">
      <button
        v-for="question in quickQuestions"
        :key="question"
        class="question-btn"
        @click="sendQuickQuestion(question)"
      >
        {{ question }}
      </button>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <input
        v-model="inputText"
        type="text"
        class="message-input"
        :placeholder="inputPlaceholder"
        :disabled="!isConnected"
        @keyup.enter="sendMessage"
      />
      <button
        class="send-btn"
        :disabled="!canSend"
        @click="sendMessage"
      >
        发送
      </button>
    </div>

    <!-- 用户名输入弹窗 -->
    <div v-if="pageStatus === 'username_input'" class="modal-overlay">
      <div class="modal">
        <h2 class="modal-title">欢迎使用智能客服</h2>
        <p class="modal-desc">请输入您的称呼，我们好为您服务</p>
        <input
          v-model="usernameInput"
          type="text"
          class="username-input"
          placeholder="例如：王先生"
          maxlength="20"
          @keyup.enter="submitUsername"
        />
        <p v-if="usernameError" class="error-text">{{ usernameError }}</p>
        <button class="submit-btn" @click="submitUsername" :disabled="isSubmitting">
          {{ isSubmitting ? '提交中...' : '开始咨询' }}
        </button>
      </div>
    </div>

    <!-- 初始化中遮罩 -->
    <div v-if="pageStatus === 'initializing'" class="modal-overlay">
      <div class="loading">
        <div class="loading-spinner"></div>
        <p>正在为你连接智能客服助手...</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { initAnonymousUser, initSession } from '@/api'
import { ChatWebSocket } from '@/utils/websocket'
import type { Message, CardAction } from '@/types'

const userStore = useUserStore()
const chatStore = useChatStore()

// 使用 storeToRefs 保持响应性
const {
  messages,
  connectionStatus,
  pageStatus,
  inputText,
  isBotProcessing,
  quickQuestionsVisible,
  quickQuestions,
} = storeToRefs(chatStore)

// 方法直接解构
const { addMessage, updateMessageStatus } = chatStore

// 本地状态
const usernameInput = ref('')
const usernameError = ref('')
const isSubmitting = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
let ws: ChatWebSocket | null = null

// 计算属性
const isConnected = computed(() => {
  return connectionStatus.value === 'connected'
})

const canSend = computed(() => {
  return isConnected.value && inputText.value.trim() && !isBotProcessing.value
})

const inputPlaceholder = computed(() => {
  if (connectionStatus.value !== 'connected') {
    return '连接中...'
  }
  return '请输入你遇到的问题，例如"这个订单为什么不能退款"'
})

const statusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connecting':
      return '正在连接...'
    case 'reconnecting':
      return '连接不稳定，正在恢复...'
    case 'failed':
      return '连接失败，请重试'
    default:
      return ''
  }
})

const statusClass = computed(() => {
  return {
    'status-warning': connectionStatus.value === 'reconnecting',
    'status-error': connectionStatus.value === 'failed',
  }
})

// 初始化
onMounted(() => {
  if (userStore.userInfo) {
    // 已有用户信息，直接连接
    connectWebSocket()
    pageStatus.value = 'chatting'
  } else {
    // 首次进入，显示用户名输入
    pageStatus.value = 'username_input'
  }
})

// 提交用户名
const submitUsername = async () => {
  if (!usernameInput.value.trim()) {
    usernameError.value = '请输入用户名'
    return
  }

  isSubmitting.value = true
  usernameError.value = ''

  try {
    const result = await initAnonymousUser(usernameInput.value.trim())
    userStore.saveToStorage(result)
    
    pageStatus.value = 'initializing'
    
    // 初始化会话
    await initSession(result.anonymous_user_id, result.anonymous_user_token)
    
    // 连接 WebSocket
    connectWebSocket()
    
    pageStatus.value = 'chatting'
  } catch (error: any) {
    usernameError.value = error.response?.data?.detail || '初始化失败，请重试'
  } finally {
    isSubmitting.value = false
  }
}

// 连接 WebSocket
const connectWebSocket = () => {
  const user = userStore.userInfo
  if (!user) return

  ws = new ChatWebSocket('')
  
  ws.onMessage((message: Message) => {
    addMessage(message)
    scrollToBottom()
    
    // 如果是机器人消息，停止处理中状态
    if (message.sender === 'bot') {
      isBotProcessing.value = false
    }
  })

  ws.onStatus((status) => {
    connectionStatus.value = status
  })

  ws.connect(user.anonymous_user_token, user.session_id)
}

// 发送消息
const sendMessage = () => {
  const content = inputText.value.trim()
  if (!content || !ws) return

  // 添加用户消息
  const userMessage: Message = {
    message_id: `msg_${Date.now()}`,
    type: 'user_text',
    content,
    sender: 'user',
    timestamp: new Date().toISOString(),
    status: 'sending',
  }
  addMessage(userMessage)
  scrollToBottom()

  // 发送
  try {
    ws.send(content)
    inputText.value = ''
    isBotProcessing.value = true
  } catch (error) {
    updateMessageStatus(userMessage.message_id, 'failed')
  }
}

// 发送快捷问题
const sendQuickQuestion = (question: string) => {
  inputText.value = question
  sendMessage()
  quickQuestionsVisible.value = false
}

// 处理卡片操作
const handleCardAction = (action: CardAction) => {
  console.log('Card action clicked', action)
  // TODO: 实现工单提交等操作
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// 格式化时间
const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #f5f5f5;
}

.header {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  background-color: #4a90d9;
  color: white;
  font-size: 17px;
  font-weight: 500;
  flex-shrink: 0;
}

.status-bar {
  padding: 8px;
  text-align: center;
  font-size: 13px;
  background-color: #fff3cd;
  color: #856404;
  flex-shrink: 0;
}

.status-warning {
  background-color: #fff3cd;
  color: #856404;
}

.status-error {
  background-color: #f8d7da;
  color: #721c24;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message-item {
  display: flex;
  margin-bottom: 16px;
}

.message-item.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 16px;
  background-color: white;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

.message-item.user .message-bubble {
  background-color: #4a90d9;
  color: white;
}

.message-bubble.processing {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
}

.processing-dot {
  animation: bounce 1.4s infinite ease-in-out;
  font-size: 8px;
}

.processing-dot:nth-child(1) { animation-delay: -0.32s; }
.processing-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.text-content {
  line-height: 1.5;
  word-wrap: break-word;
}

.card {
  padding: 12px;
  border-radius: 8px;
  background-color: #f8f9fa;
  border-left: 4px solid #4a90d9;
}

.card.success {
  border-left-color: #28a745;
}

.card.not_allowed,
.card.fail {
  border-left-color: #dc3545;
}

.card-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.card-description {
  font-size: 14px;
  color: #666;
  margin-bottom: 12px;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 12px;
  border: 1px solid #4a90d9;
  background-color: white;
  color: #4a90d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.action-btn:active {
  background-color: #4a90d9;
  color: white;
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  text-align: right;
}

.message-item.user .message-time {
  color: rgba(255,255,255,0.8);
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
  background-color: white;
  border-top: 1px solid #eee;
}

.question-btn {
  padding: 8px 16px;
  border: 1px solid #4a90d9;
  background-color: white;
  color: #4a90d9;
  border-radius: 16px;
  cursor: pointer;
  font-size: 13px;
}

.question-btn:active {
  background-color: #4a90d9;
  color: white;
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background-color: white;
  border-top: 1px solid #eee;
}

.message-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #ddd;
  border-radius: 20px;
  font-size: 15px;
  outline: none;
}

.message-input:focus {
  border-color: #4a90d9;
}

.message-input:disabled {
  background-color: #f5f5f5;
}

.send-btn {
  padding: 10px 20px;
  background-color: #4a90d9;
  color: white;
  border: none;
  border-radius: 20px;
  font-size: 15px;
  cursor: pointer;
}

.send-btn:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background-color: white;
  padding: 24px;
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
}

.modal-title {
  font-size: 20px;
  margin-bottom: 8px;
}

.modal-desc {
  font-size: 14px;
  color: #666;
  margin-bottom: 16px;
}

.username-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 15px;
  margin-bottom: 8px;
}

.error-text {
  color: #dc3545;
  font-size: 13px;
  margin-bottom: 12px;
}

.submit-btn {
  width: 100%;
  padding: 12px;
  background-color: #4a90d9;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
}

.submit-btn:disabled {
  background-color: #ccc;
}

.loading {
  text-align: center;
  color: white;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
