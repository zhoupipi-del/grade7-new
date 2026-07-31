import { defineStore } from 'pinia'
import type { UserInfo, UserRole } from '@/types'
import { parseUserRole, ROLE_LABELS } from '@/types'

/**
 * User Store — JWT Token + RBAC Role Management (W3-FE-RBAC-A)
 *
 * Token is stored in LocalStorage via pinia-plugin-persistedstate.
 * school_id is NEVER manually passed in request params — it is encoded in the JWT.
 *
 * Role parsing: raw role from backend is validated via parseUserRole().
 * Unknown roles → isRoleValid=false, role=null — fail closed, no auto-downgrade.
 */

interface UserState {
  token: string
  userInfo: UserInfo | null
  /** Raw role string from backend (before parsing), for audit logging */
  rawRole: string
  /** Whether the current role passed validation — false = fail-closed */
  isRoleValid: boolean
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: '',
    userInfo: null,
    rawRole: '',
    isRoleValid: false,
  }),

  getters: {
    isLoggedIn: (state): boolean => !!state.token,
    currentRole(): UserRole | null {
      if (!this.isRoleValid) return null
      return this.userInfo?.role ?? null
    },
    currentRoleLabel(): string {
      if (!this.isRoleValid || !this.userInfo?.role) return '角色未配置'
      return ROLE_LABELS[this.userInfo.role] ?? '未知角色'
    },
    schoolId(): number | null {
      return this.userInfo?.school_id ?? null
    },
    /** 千人千面: 当前学段 */
    currentPhase(): string {
      return this.userInfo?.school_phase ?? 'junior'
    },
    /** 千人千面: 插件配置 */
    pluginConfig(): Record<string, any> | null {
      return this.userInfo?.plugin_config ?? null
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
     * W3-FE-RBAC-A: 角色解析使用 parseUserRole()，未知角色安全拒绝。
     * 不使用 `as UserRole` 断言，不自动降级。
     */
    setUserInfo(raw: Record<string, any>) {
      const rawRoleStr = raw.role ?? ''
      this.rawRole = rawRoleStr

      const roleResult = parseUserRole(rawRoleStr)
      this.isRoleValid = roleResult.ok

      if (!roleResult.ok) {
        // Unknown role — fail closed, log security warning
        console.warn(
          `[UserStore] Unknown role "${rawRoleStr}" rejected — session invalid, fail-closed.`
        )
      }

      this.userInfo = {
        id: raw.id ?? 0,
        username: raw.username ?? '',
        real_name: raw.real_name || raw.display_name || '',
        role: roleResult.ok ? roleResult.role : null,
        school_id: raw.school_id ?? 0,
        school_name: raw.school_name || '',
        school_phase: raw.school_phase || 'junior',
        plugin_config: raw.plugin_config ?? null,
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
      this.rawRole = ''
      this.isRoleValid = false
    },
  },

  persist: {
    key: 'wings3_user',
    storage: localStorage,
    paths: ['token', 'userInfo', 'rawRole', 'isRoleValid'],
  },
})
