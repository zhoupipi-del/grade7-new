<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <img src="/favicon.svg" alt="logo" class="login-logo" />
        <h1 class="login-title">Wings 3.0</h1>
        <p class="login-subtitle">梨江中学德育管理平台</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <p>多租户 SaaS 架构 · JWT 认证 · RBAC 权限</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { useTenantStore } from '@/store/tenant'
import { login as loginApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const tenantStore = useTenantStore()

const loginFormRef = ref<FormInstance>()
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      // 釜底抽薪：直接用原生 fetch 绕过所有 axios 拦截器/默认配置
      // 确保 Content-Type: application/json + 标准 JSON body
      const apiUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1') + '/auth/login'
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          username: loginForm.username,
          password: loginForm.password,
        }),
      })

      const res: any = await response.json()

      if (!response.ok) {
        // 后端返回错误（401/422/500 等）
        const detail = res?.detail || res?.message || `HTTP ${response.status}`
        ElMessage.error(`登录失败：${detail}`)
        console.error('[Login Error]', response.status, res)
        return
      }

      // Store JWT token
      userStore.setToken(res.access_token)

      // Store user info
      if (res.user) {
        userStore.setUserInfo(res.user)
        // Set tenant context from user info
        if (res.user.school_id && res.user.school_name) {
          tenantStore.setSchool(res.user.school_id, res.user.school_name)
        }
      }

      ElMessage.success('登录成功')

      // Redirect to original page or home
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
    } catch (error: any) {
      ElMessage.error('网络异常，请检查网络连接')
      console.error('[Login Error]', error)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  position: relative;
  z-index: 1;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-card {
  width: 420px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-logo {
  width: 64px;
  height: 64px;
  margin-bottom: 12px;
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  color: #1f2c3f;
  margin-bottom: 6px;
}

.login-subtitle {
  font-size: 14px;
  color: #909399;
}

.login-form {
  margin-bottom: 20px;
}

.login-btn {
  width: 100%;
  font-size: 16px;
  letter-spacing: 4px;
}

.login-footer {
  text-align: center;
  margin-top: 20px;
}

.login-footer p {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
