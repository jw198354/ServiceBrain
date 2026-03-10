import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message, ConnectionStatus, PageStatus } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const pageStatus = ref<PageStatus>('uninitialized')
  const inputText = ref('')
  const isBotProcessing = ref(false)
  const quickQuestionsVisible = ref(true)
  
  // 快捷问题
  const quickQuestions = [
    '退款多久到账？',
    '帮我查订单物流',
    '这个订单能退款吗？',
    '售后规则说明',
  ]
  
  // 添加消息
  const addMessage = (message: Message) => {
    messages.value.push(message)
  }
  
  // 更新消息状态
  const updateMessageStatus = (messageId: string, status: 'sending' | 'sent' | 'failed') => {
    const msg = messages.value.find(m => m.message_id === messageId)
    if (msg) {
      msg.status = status
    }
  }
  
  // 清空消息
  const clearMessages = () => {
    messages.value = []
  }
  
  return {
    messages,
    connectionStatus,
    pageStatus,
    inputText,
    isBotProcessing,
    quickQuestionsVisible,
    quickQuestions,
    addMessage,
    updateMessageStatus,
    clearMessages,
  }
})
