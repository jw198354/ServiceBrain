// 消息类型
export type MessageType =
  | 'user_text'
  | 'bot_greeting'
  | 'bot_text'
  | 'bot_followup'
  | 'bot_knowledge'
  | 'bot_explain'
  | 'tool_result_card'
  | 'ticket_card'
  | 'system_status'
  | 'error_message'

// 消息内容
export interface Message {
  message_id: string
  type: MessageType
  content: string
  sender: 'user' | 'bot' | 'system'
  timestamp: string
  status?: 'sending' | 'sent' | 'failed'
  card?: ToolResultCard | TicketCard
}

// 工具结果卡片
export interface ToolResultCard {
  message_type: 'tool_result_card'
  title: string
  description: string
  status: 'success' | 'not_allowed' | 'fail' | 'need_more_info'
  actions?: CardAction[]
}

// 工单卡片
export interface TicketCard {
  message_type: 'ticket_card'
  title: string
  description: string
  summary?: string
  actions?: CardAction[]
  status?: 'suggested' | 'submitted' | 'created'
}

// 卡片操作按钮
export interface CardAction {
  label: string
  action: string
  payload?: Record<string, any>
}

// 用户信息
export interface UserInfo {
  anonymous_user_id: string
  anonymous_user_token: string
  username: string
  session_id: string
}

// 连接状态
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed'

// 页面状态
export type PageStatus = 
  | 'uninitialized'
  | 'username_input'
  | 'initializing'
  | 'ready'
  | 'chatting'
