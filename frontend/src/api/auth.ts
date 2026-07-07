import request from './request'
import type { LoginPayload, LoginResponse } from '@/types'

/**
 * Authentication API
 *
 * 注意: 后端 UserOut 的字段与前端 UserInfo 不同：
 *   - display_name (前端用 real_name)
 *   - role: "ms_admin" 小写 (前端用 "MS_ADMIN" 大写)
 *   - 可能缺少 class_name / grade_name
 *
 * 所有归一化在 userStore.setUserInfo() 中处理，API层透传原始数据。
 */

export function login(payload: LoginPayload): Promise<LoginResponse> {
  return request.post('/auth/login', {
    username: payload.username,
    password: payload.password,
  })
}

/**
 * GET /auth/me — 返回后端 UserOut 原始格式
 * 透传给 userStore.setUserInfo() 做归一化
 */
export function getCurrentUser(): Promise<Record<string, any>> {
  return request.get('/auth/me')
}

export function logout(): Promise<void> {
  return request.post('/auth/logout')
}
