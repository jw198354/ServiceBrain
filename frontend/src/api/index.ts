import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
})

// 匿名用户初始化
export async function initAnonymousUser(username: string) {
  const response = await api.post('/user/init-anonymous', { username })
  return response.data
}

// 会话初始化
export async function initSession(anonymous_user_id: string, anonymous_user_token: string) {
  const response = await api.post('/session/init', {
    anonymous_user_id,
    anonymous_user_token,
  })
  return response.data
}

// 获取历史消息
export async function getMessages(session_id: string, limit = 50) {
  const response = await api.get(`/session/${session_id}/messages?limit=${limit}`)
  return response.data
}

// 创建工单
export async function createTicket(session_id: string, summary: string) {
  const response = await api.post('/ticket/create', null, {
    params: { session_id, summary },
  })
  return response.data
}

export default api
