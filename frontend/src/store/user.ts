import { defineStore } from 'pinia'
import type { UserInfo, UserRole } from '@/types'
import type { Workstation } from '@/api/workstation'

/**
 * User Store — JWT Token + RBAC Role Management + Workstation（工作台身份）
 *
 * Token is stored in LocalStorage via pinia-plugin-persistedstate.
 * school_id is NEVER manually passed in request params — it is encoded in the JWT.
 *
 * Workstation（2026-08-13 周主任拍板）：
 *   一个老师可同时是班主任+年级组长+任课教师 → 登录后拉取 /me/workstations，
 *   默认进入最主要工作台，可切换；菜单随身份收敛到 ≤5 个一级入口。
 */

interface UserState {
  token: string
  userInfo: UserInfo | null
  workstations: Workstation[]
  currentIdentity: string | null
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: '',
    userInfo: null,
    workstations: [],
    currentIdentity: null,
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
        TEACHER: '教师',
        COUNSELOR: '心理教师',
        PARENT: '家长',
        STUDENT: '学生',
      }
      // 🔪 Fix: 用 currentRole (已大写) 替代 userInfo.role (可能小写)
      return this.currentRole ? roleMap[this.currentRole] : '未登录'
    },
    schoolId(): number | null {
      return this.userInfo?.school_id ?? null
    },
    /** 🎯 千人千面: 当前学段 */
    currentPhase(): string {
      return this.userInfo?.school_phase ?? 'junior'
    },
    /** 🎯 千人千面: 插件配置 */
    pluginConfig(): Record<string, any> | null {
      return this.userInfo?.plugin_config ?? null
    },
    /** 当前工作台身份对象（按 currentIdentity 查找） */
    currentWorkstation(): Workstation | null {
      return this.workstations.find((w) => w.identity === this.currentIdentity) ?? null
    },
    /** 当前工作台标题（如：2501班班主任） */
    currentWorkstationTitle(): string {
      return this.currentWorkstation?.title ?? this.currentRoleLabel
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
        // 🎯 千人千面: 学段 + 插件配置
        school_phase: raw.school_phase || 'junior',
        plugin_config: raw.plugin_config ?? null,
        class_id: raw.class_id ?? null,
        class_name: raw.class_name ?? null,
        grade_id: raw.grade_id ?? null,
        grade_name: raw.grade_name ?? null,
        avatar: raw.avatar ?? null,
      }
    },

    /** 🎯 工作台：保存身份列表并选中默认身份 */
    setWorkstations(workstations: Workstation[], defaultIdentity: string | null) {
      this.workstations = workstations || []
      if (defaultIdentity && this.workstations.some((w) => w.identity === defaultIdentity)) {
        this.currentIdentity = defaultIdentity
      } else {
        this.currentIdentity = this.workstations[0]?.identity ?? null
      }
    },

    /** 🎯 工作台：切换当前身份 */
    switchIdentity(identity: string) {
      if (this.workstations.some((w) => w.identity === identity)) {
        this.currentIdentity = identity
      }
    },

    clearAuth() {
      this.token = ''
      this.userInfo = null
      this.workstations = []
      this.currentIdentity = null
    },
  },

  persist: {
    key: 'wings3_user',
    storage: localStorage,
    paths: ['token', 'userInfo', 'workstations', 'currentIdentity'],
  },
})
