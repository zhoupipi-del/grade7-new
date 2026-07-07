import { defineStore } from 'pinia'

/**
 * Tenant Store — Multi-Tenant School Context
 *
 * Manages the current school context for multi-tenant SaaS.
 * In single-tenant mode, this defaults to "梨江中学".
 */

interface TenantState {
  schoolId: number
  schoolName: string
}

export const useTenantStore = defineStore('tenant', {
  state: (): TenantState => ({
    schoolId: 1,
    schoolName: '梨江中学',
  }),

  getters: {
    currentSchoolName: (state): string => state.schoolName,
  },

  actions: {
    setSchool(id: number, name: string) {
      this.schoolId = id
      this.schoolName = name
    },
  },

  persist: {
    key: 'wings3_tenant',
    storage: localStorage,
  },
})
