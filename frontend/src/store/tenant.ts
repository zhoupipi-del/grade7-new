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
  schoolPhase: string
}

export const useTenantStore = defineStore('tenant', {
  state: (): TenantState => ({
    schoolId: 1,
    schoolName: '梨江中学',
    schoolPhase: 'junior',
  }),

  getters: {
    currentSchoolName: (state): string => state.schoolName,
    currentSchoolPhase: (state): string => state.schoolPhase,
  },

  actions: {
    setSchool(id: number, name: string, phase?: string) {
      this.schoolId = id
      this.schoolName = name
      if (phase) this.schoolPhase = phase
    },
  },

  persist: {
    key: 'wings3_tenant',
    storage: localStorage,
  },
})
