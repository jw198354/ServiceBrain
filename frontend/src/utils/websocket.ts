import type { Message, ConnectionStatus } from '@/types'

export type MessageHandler = (message: Message) => void
export type StatusHandler = (status: ConnectionStatus, data?: any) => void

export class ChatWebSocket {
  private ws: WebSocket | null = null
  private url: string = ''
  private reconnectAttempts = 0
  private maxReconnectAttempts = 3
  private reconnectDelays = [1000, 2000, 5000] // 指数退避
  private pingInterval: number | null = null
  private messageHandlers: MessageHandler[] = []
  private statusHandlers: StatusHandler[] = []
  private shouldReconnect = true

  constructor(baseUrl: string) {
    // WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // 开发环境使用 localhost:8000，生产环境使用当前 host
    const isDev = import.meta.env.DEV
    const host = isDev ? 'localhost:8000' : window.location.host
    this.url = `${wsProtocol}//${host}/ws/chat`
  }

  // 连接
  connect(token: string, sessionId: string) {
    this.shouldReconnect = true
    this.reconnectAttempts = 0
    
    const url = `${this.url}?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('WebSocket connected')
      this.updateStatus('connected')
      this.startPing()
    }

    this.ws.onclose = (event) => {
      console.log('WebSocket closed', event.code, event.reason)
      this.stopPing()
      this.updateStatus('disconnected')
      
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.scheduleReconnect(token, sessionId)
      }
    }

    this.ws.onerror = (error) => {
      console.error('WebSocket error', error)
      this.updateStatus('failed', { error })
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.handleMessage(data)
      } catch (e) {
        console.error('Failed to parse message', e)
      }
    }
  }

  // 重连
  private scheduleReconnect(token: string, sessionId: string) {
    const delay = this.reconnectDelays[this.reconnectAttempts] || 5000
    this.reconnectAttempts++
    
    console.log(`Scheduling reconnect attempt ${this.reconnectAttempts} in ${delay}ms`)
    this.updateStatus('reconnecting', { attempt: this.reconnectAttempts })
    
    setTimeout(() => {
      if (this.shouldReconnect) {
        this.connect(token, sessionId)
      }
    }, delay)
  }

  // 处理消息
  private handleMessage(data: any) {
    switch (data.type) {
      case 'system':
        this.handleSystemMessage(data)
        break
      case 'bot_message':
        this.handleBotMessage(data)
        break
      case 'ack':
        this.handleAck(data)
        break
      case 'pong':
        // Ping 响应，无需处理
        break
      default:
        console.warn('Unknown message type', data.type)
    }
  }

  private handleSystemMessage(data: any) {
    const message: Message = {
      message_id: `sys_${Date.now()}`,
      type: 'system_status',
      content: data.message,
      sender: 'system',
      timestamp: new Date().toISOString(),
    }
    this.notifyMessageHandlers(message)
  }

  private handleBotMessage(data: any) {
    const payload = data.payload || {}
    const message: Message = {
      message_id: data.message_id,
      type: payload.message_type || data.type,
      content: payload.content || '',
      sender: 'bot',
      timestamp: new Date().toISOString(),
      card: payload.card,
      payload: payload,
    }
    this.notifyMessageHandlers(message)
  }

  private handleAck(data: any) {
    // ACK 处理，更新消息状态
    console.log('Message acknowledged', data.message_id, data.status)
  }

  // 发送消息
  send(content: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected')
    }

    const message = {
      type: 'user_message',
      message_id: `msg_${Date.now()}`,
      session_id: this.getSessionId(),
      trace_id: `trace_${Date.now()}`,
      content,
      timestamp: Date.now(),
    }

    this.ws.send(JSON.stringify(message))
    return message.message_id
  }

  // 发送 ping
  private startPing() {
    this.stopPing()
    this.pingInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'ping',
          timestamp: Date.now(),
        }))
      }
    }, 20000) // 20 秒
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  // 断开连接
  disconnect() {
    this.shouldReconnect = false
    this.stopPing()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  // 状态管理
  private updateStatus(status: ConnectionStatus, data?: any) {
    this.statusHandlers.forEach(handler => handler(status, data))
  }

  // 获取 session_id（从 localStorage）
  private getSessionId(): string {
    const user = localStorage.getItem('servicebrain_user')
    if (user) {
      try {
        return JSON.parse(user).session_id
      } catch (e) {
        console.error('Failed to get session_id from storage', e)
      }
    }
    return ''
  }

  // 注册消息处理器
  onMessage(handler: MessageHandler) {
    this.messageHandlers.push(handler)
  }

  // 注册状态处理器
  onStatus(handler: StatusHandler) {
    this.statusHandlers.push(handler)
  }

  // 通知消息处理器
  private notifyMessageHandlers(message: Message) {
    this.messageHandlers.forEach(handler => handler(message))
  }
}
