import { defineStore } from 'pinia'
import type { UserInfo, UserRole } from '@/types'

/**
 * User Store — JWT Token + RBAC Role Management
 *
 * Token is stored in LocalStorage via pinia-plugin-persistedstate.
 * school_id is NEVER manually passed in request params — it is encoded in the JWT.
 */

interface UserState {
  token: string
  userInfo: UserInfo | null
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: '',
    userInfo: null,
  }),

  getters: {
    isLoggedIn: (state): boolean => !!state.token,
    currentRole(): UserRole | null {
      // setUserInfo() 已归一化为大写 UserRole，直接取值即可
      return this.userInfo?.role ?? null
    },
    currentRoleLabel(): string {
      const roleMap: Record<UserRole, string> = {
        MS_ADMIN: '德育处管理员',
        GRADE_LEADER: '年级组长',
        CLASS_TEACHER: '班主任',
        PARENT: '家长',
        STUDENT: '学生',
      }
      // 🔪 Fix: 用 currentRole (已大写) 替代 userInfo.role (可能小写)
      return this.currentRole ? roleMap[this.currentRole] : '未登录'
    },
    schoolId(): number | null {
      return this.userInfo?.school_id ?? null
    },
  },

  actions: {
    setToken(token: string) {
      this.token = token
    },

    /**
     * 归一化写入 UserInfo — 后端与前端字段对齐
     *
     * 后端 UserOut 格式:
     *   display_name (前端用 real_name)
     *   role: "ms_admin" (前端用 "MS_ADMIN" 大写 UserRole)
     *   class_name/grade_name 可能缺失
     *
     * 此方法在边界层做翻译，下游代码始终拿到规范化的 UserInfo。
     */
    setUserInfo(raw: Record<string, any>) {
      this.userInfo = {
        id: raw.id ?? 0,
        username: raw.username ?? '',
        // 🔪 Fix: 后端 display_name → 前端 real_name
        real_name: raw.real_name || raw.display_name || '',
        // 🔪 Fix: 后端 "ms_admin" → 前端 "MS_ADMIN"
        role: (typeof raw.role === 'string' ? raw.role.toUpperCase() : raw.role) as UserRole,
        school_id: raw.school_id ?? 0,
        school_name: raw.school_name || '',
        class_id: raw.class_id ?? null,
        class_name: raw.class_name ?? null,
        grade_id: raw.grade_id ?? null,
        grade_name: raw.grade_name ?? null,
        avatar: raw.avatar ?? null,
      }
    },

    clearAuth() {
      this.token = ''
      this.userInfo = null
    },
  },

  persist: {
    key: 'wings3_user',
    storage: localStorage,
    paths: ['token', 'userInfo'],
  },
})
