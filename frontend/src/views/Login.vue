<template>
  <div class="login-container">
    <!-- 左侧品牌展板 -->
    <div class="login-brand">
      <div class="brand-inner">
        <div class="brand-logo-wrap">
          <img src="/favicon.svg" alt="logo" class="brand-logo" />
        </div>
        <h1 class="brand-title">Wings 3.0</h1>
        <p class="brand-sub">梨江中学德育管理平台</p>

        <ul class="brand-feats">
          <li>
            <span class="feat-ico"><el-icon><DataLine /></el-icon></span>
            德育风险一图统揽 · 实时态势感知
          </li>
          <li>
            <span class="feat-ico"><el-icon><Stamp /></el-icon></span>
            违纪 → 处分 → 评价 全流程闭环
          </li>
          <li>
            <span class="feat-ico"><el-icon><MagicStick /></el-icon></span>
            AI 德育处方辅助精准干预
          </li>
        </ul>

        <p class="brand-foot">多租户 SaaS 架构 · JWT 认证 · RBAC 权限</p>
      </div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="login-panel">
      <div class="login-card">
        <div class="login-header">
          <img src="/favicon.svg" alt="logo" class="login-logo" />
          <h2 class="login-title">欢迎登录</h2>
          <p class="login-subtitle">请输入您的账号信息</p>
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
          <p>梨江中学 · 德育数据中台</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, DataLine, Stamp, MagicStick } from '@element-plus/icons-vue'
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
        // Set tenant context from user info (含学段)
        if (res.user.school_id && res.user.school_name) {
          tenantStore.setSchool(
            res.user.school_id,
            res.user.school_name,
            res.user.school_phase,
          )
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
  min-height: 100vh;
  display: flex;
}

/* ═══ 左侧品牌展板 ═══ */
.login-brand {
  flex: 0 0 44%;
  background: linear-gradient(135deg, #1e6091 0%, #184d74 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  position: relative;
  overflow: hidden;
}

/* 装饰光斑 */
.login-brand::before,
.login-brand::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.07);
}
.login-brand::before {
  width: 340px;
  height: 340px;
  top: -90px;
  right: -90px;
}
.login-brand::after {
  width: 260px;
  height: 260px;
  bottom: -70px;
  left: -70px;
}

.brand-inner {
  position: relative;
  z-index: 1;
  max-width: 380px;
  width: 100%;
}

.brand-logo-wrap {
  margin-bottom: 22px;
}
.brand-logo {
  width: 72px;
  height: 72px;
  background: #fff;
  border-radius: 18px;
  padding: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

.brand-title {
  font-size: 34px;
  font-weight: 800;
  margin: 0 0 6px;
  letter-spacing: 1px;
}
.brand-sub {
  font-size: 16px;
  opacity: 0.85;
  margin: 0 0 36px;
}

.brand-feats {
  list-style: none;
  padding: 0;
  margin: 0 0 40px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.brand-feats li {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 15px;
  opacity: 0.92;
}
.feat-ico {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 10px;
  font-size: 18px;
}
.brand-foot {
  font-size: 13px;
  opacity: 0.6;
  margin: 0;
}

/* ═══ 右侧登录面板 ═══ */
.login-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  padding: 40px;
}

.login-card {
  width: 380px;
  max-width: 100%;
  padding: 36px 32px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 10px 40px rgba(16, 24, 40, 0.08);
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}
.login-logo {
  width: 56px;
  height: 56px;
  margin-bottom: 10px;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  color: #1f2933;
  margin: 0 0 6px;
}
.login-subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.login-form {
  margin-bottom: 10px;
}

.login-btn {
  width: 100%;
  font-size: 16px;
  letter-spacing: 4px;
}

.login-footer {
  text-align: center;
  margin-top: 18px;
}
.login-footer p {
  font-size: 12px;
  color: #c0c4cc;
  margin: 0;
}

/* ═══ 响应式：窄屏隐藏品牌展板 ═══ */
@media (max-width: 860px) {
  .login-brand {
    display: none;
  }
  .login-panel {
    background: linear-gradient(135deg, #1e6091 0%, #184d74 100%);
  }
}
</style>
