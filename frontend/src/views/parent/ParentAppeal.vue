<template>
  <div class="parent-appeal">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><WarningFilled /></el-icon>
        在线申诉
      </h2>
      <p class="page-subtitle">对处分或违纪记录提出申诉，系统将自动路由到对应审批部门</p>
    </div>

    <el-row :gutter="16">
      <!-- 左栏: 申诉表单 -->
      <el-col :span="16">
        <el-card shadow="hover" class="appeal-form-card">
          <template #header>
            <span class="card-title">
              <el-icon><EditPen /></el-icon>
              申诉信息填写
            </span>
          </template>

          <el-form
            ref="appealFormRef"
            :model="appealForm"
            :rules="appealRules"
            label-width="100px"
            class="appeal-form"
          >
            <!-- 申诉类型选择 -->
            <el-form-item label="申诉类型" prop="target_module">
              <div class="target-selector">
                <div
                  v-for="opt in APPEAL_TARGET_OPTIONS"
                  :key="opt.value"
                  class="target-card"
                  :class="{ active: appealForm.target_module === opt.value }"
                  @click="selectTarget(opt.value as AppealTargetModule)"
                >
                  <el-icon :size="24" class="target-icon">
                    <component :is="opt.value === 'discipline' ? 'Stamp' : 'Warning'" />
                  </el-icon>
                  <div class="target-info">
                    <div class="target-label">{{ opt.label }}</div>
                    <div class="target-desc">{{ APPEAL_TARGET_META[opt.value].description }}</div>
                  </div>
                  <el-icon v-if="appealForm.target_module === opt.value" class="check-icon">
                    <CircleCheckFilled />
                  </el-icon>
                </div>
              </div>
            </el-form-item>

            <!-- 记录ID -->
            <el-form-item label="记录编号" prop="target_record_id">
              <el-input-number
                v-model="appealForm.target_record_id"
                :min="1"
                placeholder="请输入要申诉的记录编号"
                style="width: 100%"
                controls-position="right"
              />
              <div class="form-hint">
                <el-icon><InfoFilled /></el-icon>
                记录编号可在「惩戒流转中心」或「德育与处分中心」查看
              </div>
            </el-form-item>

            <!-- 申诉人姓名 -->
            <el-form-item label="申诉人姓名" prop="applicant_name">
              <el-input
                v-model="appealForm.applicant_name"
                placeholder="请输入申诉人姓名（家长姓名）"
                maxlength="50"
              />
            </el-form-item>

            <!-- 联系电话 -->
            <el-form-item label="联系电话" prop="applicant_phone">
              <el-input
                v-model="appealForm.applicant_phone"
                placeholder="请输入联系电话（选填）"
                maxlength="20"
              />
            </el-form-item>

            <!-- 申诉事由 -->
            <el-form-item label="申诉事由" prop="reason">
              <el-input
                v-model="appealForm.reason"
                type="textarea"
                :rows="6"
                placeholder="请详细描述申诉事由，包括事实经过、申诉理由及相关证据说明..."
                maxlength="2000"
                show-word-limit
              />
            </el-form-item>

            <!-- 血缘追踪提示 -->
            <el-alert
              title="操作溯源声明"
              type="info"
              :closable="false"
              class="trace-alert"
            >
              <template #default>
                本次申诉操作将通过血缘追踪机制记录来源上下文（操作人、IP地址、时间戳、渠道），
                确保申诉流程可追溯、可审计。
              </template>
            </el-alert>

            <!-- 提交按钮 -->
            <el-form-item class="submit-row">
              <el-button
                type="warning"
                size="large"
                :loading="submitting"
                :icon="Promotion"
                @click="submitAppeal"
              >
                提交申诉
              </el-button>
              <el-button size="large" @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右栏: 申诉说明 + 历史记录 -->
      <el-col :span="8">
        <!-- 申诉流程说明 -->
        <el-card shadow="hover" class="guide-card">
          <template #header>
            <span class="card-title">
              <el-icon><Guide /></el-icon>
              申诉流程
            </span>
          </template>
          <el-steps direction="vertical" :active="0" class="appeal-steps">
            <el-step title="提交申诉" description="家长填写申诉表单并提交" />
            <el-step title="自动路由" description="系统将申诉路由到对应审批部门" />
            <el-step title="部门审核" description="德育处/年级组审核申诉材料" />
            <el-step title="结果通知" description="审核结果通过通知推送给家长" />
          </el-steps>
        </el-card>

        <!-- 注意事项 -->
        <el-card shadow="hover" class="notice-card">
          <template #header>
            <span class="card-title">
              <el-icon><Warning /></el-icon>
              注意事项
            </span>
          </template>
          <ul class="notice-list">
            <li>申诉需在处分生效后 <b>7个工作日</b> 内提出</li>
            <li>每条记录仅可申诉 <b>一次</b>，请确保材料完整</li>
            <li>申诉期间处分继续执行，不暂停</li>
            <li>如有证据材料，请在申诉事由中说明并线下提交</li>
            <li>恶意申诉将影响后续申诉权限</li>
          </ul>
        </el-card>
      </el-col>
    </el-row>

    <!-- 申诉成功对话框 -->
    <el-dialog
      v-model="showSuccessDialog"
      title="申诉已提交"
      width="450px"
      :close-on-click-modal="false"
    >
      <div class="success-content">
        <el-icon :size="64" color="#67c23a" class="success-icon">
          <CircleCheckFilled />
        </el-icon>
        <h3 class="success-title">申诉提交成功</h3>
        <p class="success-message">{{ successMessage }}</p>
        <div v-if="successResult" class="success-detail">
          <div class="detail-row">
            <span class="detail-key">申诉编号：</span>
            <span class="detail-val">#{{ successResult.target_appeal_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">路由模块：</span>
            <span class="detail-val">{{ successResult.target_module === 'discipline' ? '处分申诉' : '违纪申诉' }}</span>
          </div>
          <div v-if="successResult._meta" class="detail-row">
            <span class="detail-key">处理耗时：</span>
            <span class="detail-val">{{ successResult._meta.elapsed_ms }}ms</span>
          </div>
        </div>
        <el-button type="primary" @click="showSuccessDialog = false" class="success-btn">
          我知道了
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  CircleCheckFilled,
  EditPen,
  InfoFilled,
  Warning,
  Guide,
  Promotion,
} from '@element-plus/icons-vue'
import {
  proxyAppeal,
  APPEAL_TARGET_OPTIONS,
  APPEAL_TARGET_META,
  type AppealTargetModule,
  type AppealProxyResult,
} from '@/api/parent_portal'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const appealFormRef = ref<FormInstance>()
const submitting = ref(false)
const showSuccessDialog = ref(false)
const successMessage = ref('')
const successResult = ref<AppealProxyResult | null>(null)

const appealForm = reactive({
  target_module: '' as AppealTargetModule | '',
  target_record_id: undefined as number | undefined,
  applicant_name: '',
  applicant_phone: '',
  reason: '',
})

const appealRules: FormRules = {
  target_module: [{ required: true, message: '请选择申诉类型', trigger: 'change' }],
  target_record_id: [{ required: true, message: '请输入记录编号', trigger: 'blur' }],
  applicant_name: [{ required: true, message: '请输入申诉人姓名', trigger: 'blur' }],
  reason: [{ required: true, message: '请填写申诉事由', trigger: 'blur' }],
}

function selectTarget(module: AppealTargetModule) {
  appealForm.target_module = module
}

async function submitAppeal() {
  if (!appealFormRef.value) return
  await appealFormRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      // 获取绑定的学生ID
      const studentId = (userStore.userInfo as any)?.bound_student_id || 100

      const result = await proxyAppeal({
        target_module: appealForm.target_module as AppealTargetModule,
        target_record_id: appealForm.target_record_id!,
        student_id: studentId,
        applicant_name: appealForm.applicant_name,
        applicant_phone: appealForm.applicant_phone || undefined,
        reason: appealForm.reason,
      })

      successResult.value = result
      successMessage.value = result.message || '申诉已提交，请耐心等待审核结果'
      showSuccessDialog.value = true

      // 重置表单
      resetForm()
    } catch {
      // 错误已由 axios 拦截器处理
    } finally {
      submitting.value = false
    }
  })
}

function resetForm() {
  appealForm.target_module = ''
  appealForm.target_record_id = undefined
  appealForm.applicant_name = ''
  appealForm.applicant_phone = ''
  appealForm.reason = ''
  appealFormRef.value?.clearValidate()
}
</script>

<style scoped>
.parent-appeal {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
  margin: 0;
}

.appeal-form-card {
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}

.appeal-form {
  padding-top: 12px;
}

/* 申诉类型选择器 */
.target-selector {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.target-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e4e7ed;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.25s;
  position: relative;
}

.target-card:hover {
  border-color: #e6a23c;
  background: rgba(230, 162, 60, 0.03);
}

.target-card.active {
  border-color: #e6a23c;
  background: rgba(230, 162, 60, 0.08);
}

.target-icon {
  color: #909399;
  flex-shrink: 0;
}

.target-card.active .target-icon {
  color: #e6a23c;
}

.target-info {
  flex: 1;
}

.target-label {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.target-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.check-icon {
  color: #e6a23c;
  font-size: 20px;
  flex-shrink: 0;
}

.form-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.trace-alert {
  margin: 16px 0;
}

.submit-row {
  margin-top: 24px;
}

.submit-row :deep(.el-form-item__content) {
  justify-content: flex-start;
  gap: 12px;
}

/* 右栏 */
.guide-card,
.notice-card {
  margin-bottom: 16px;
}

.appeal-steps {
  padding: 8px 0;
}

.notice-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
  line-height: 2;
}

.notice-list li {
  margin-bottom: 4px;
}

.notice-list b {
  color: #f56c6c;
}

/* 成功对话框 */
.success-content {
  text-align: center;
  padding: 20px 0;
}

.success-icon {
  margin-bottom: 16px;
}

.success-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px 0;
}

.success-message {
  font-size: 14px;
  color: #606266;
  margin: 0 0 20px 0;
  line-height: 1.6;
}

.success-detail {
  text-align: left;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 20px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}

.detail-key {
  color: #909399;
}

.detail-val {
  color: #303133;
  font-weight: 500;
}

.success-btn {
  width: 200px;
}
</style>
