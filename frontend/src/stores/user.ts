import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserInfo } from '@/types'

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<UserInfo | null>(null)
  
  // 从 localStorage 加载
  const loadFromStorage = () => {
    const stored = localStorage.getItem('servicebrain_user')
    if (stored) {
      try {
        userInfo.value = JSON.parse(stored)
      } catch (e) {
        console.error('Failed to load user info from storage', e)
      }
    }
  }
  
  // 保存到 localStorage
  const saveToStorage = (user: UserInfo) => {
    userInfo.value = user
    localStorage.setItem('servicebrain_user', JSON.stringify(user))
  }
  
  // 清除存储
  const clearStorage = () => {
    userInfo.value = null
    localStorage.removeItem('servicebrain_user')
  }
  
  // 初始化时加载
  loadFromStorage()
  
  return {
    userInfo,
    saveToStorage,
    clearStorage,
    loadFromStorage,
  }
})
