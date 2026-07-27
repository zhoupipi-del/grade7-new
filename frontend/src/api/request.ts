import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/user'

/**
 * Wings 3.0 Axios Interceptor Gateway
 *
 * - Request: auto-inject Authorization Bearer token from LocalStorage
 * - Response: centralized 401 (redirect to login), 403 (multi-tenant violation alert), 500 (server error)
 * - Timeout: 30s for AI prescription generation and heavy aggregation queries
 */

const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Request Interceptor — JWT Bearer Token Auto-Injection
 */
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error: any) => {
    console.error('[Request Error]', error)
    return Promise.reject(error)
  }
)

/**
 * Response Interceptor — Centralized Error Handling
 *
 * 401 → clear auth + redirect to /login
 * 403 → multi-tenant violation alert (ElMessageBox)
 * 500 → server error toast (ElMessage)
 */
service.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error: any) => {
    const { response } = error

    if (!response) {
      // Network error or timeout
      ElMessage.error('网络异常，请检查网络连接或稍后重试')
      return Promise.reject(error)
    }

    const status = response.status
    const detail = response.data?.detail || response.data?.message || '未知错误'

    switch (status) {
      case 401:
        // Token expired or invalid — clear auth and redirect
        ElMessage.error('登录已过期，请重新登录')
        const userStore = useUserStore()
        userStore.clearAuth()
        window.location.href = import.meta.env.BASE_URL + 'login'
        break

      case 403:
        // Multi-tenant isolation violation — show alert box
        ElMessageBox.alert(
          `多租户隔离拦截：${detail}`,
          '访问被拒绝',
          {
            confirmButtonText: '我知道了',
            type: 'warning',
          }
        )
        break

      case 404:
        ElMessage.error(`资源不存在：${detail}`)
        break

      case 422:
        // Validation error — show field-level errors
        ElMessage.error(`参数校验失败：${detail}`)
        break

      case 500:
        ElMessage.error(`服务器内部错误：${detail}`)
        console.error('[Server 500]', response.data)
        break

      default:
        ElMessage.error(`请求失败 (${status})：${detail}`)
    }

    return Promise.reject(error)
  }
)

export default service

// ═══════════════════════════════════════════════════════════════
// Type-level override: the response interceptor (line 47) unpacks
// AxiosResponse → response.data at runtime.  This augmentation
// tells TypeScript that get/post/put/delete return Promise<T>
// directly — matching actual runtime behavior across every API
// caller in the project.
// ═══════════════════════════════════════════════════════════════
declare module 'axios' {
  interface AxiosInstance {
    get<T = any>(url: string, config?: any): Promise<T>
    post<T = any>(url: string, data?: any, config?: any): Promise<T>
    put<T = any>(url: string, data?: any, config?: any): Promise<T>
    delete<T = any>(url: string, config?: any): Promise<T>
    patch<T = any>(url: string, data?: any, config?: any): Promise<T>
  }
}
