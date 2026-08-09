<template>
  <div class="parent-feedback">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><ChatLineSquare /></el-icon>
        家校反馈
      </h2>
      <el-button
        type="primary"
        :icon="Plus"
        @click="showCreateDialog = true"
        class="create-btn"
      >
        提交新反馈
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select
            v-model="filterType"
            placeholder="反馈类型"
            clearable
            @change="fetchFeedbacks"
          >
            <el-option
              v-for="opt in FEEDBACK_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select
            v-model="filterStatus"
            placeholder="处理状态"
            clearable
            @change="fetchFeedbacks"
          >
            <el-option
              v-for="opt in FEEDBACK_STATUS_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-button :icon="Refresh" @click="fetchFeedbacks" :loading="loading">
            刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 反馈列表 -->
    <el-card shadow="hover" class="list-card">
      <div v-if="loading" class="loading-state">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="feedbacks.length === 0" class="empty-state">
        <el-empty description="暂无反馈记录，点击「提交新反馈」开始沟通" />
      </div>
      <div v-else class="feedback-list">
        <div
          v-for="fb in feedbacks"
          :key="fb.id"
          class="feedback-item"
          @click="openDetail(fb)"
        >
          <div class="item-header">
            <div class="item-tags">
              <el-tag size="small" :color="getTypeColor(fb.feedback_type)" effect="light">
                {{ fb.feedback_type_label }}
              </el-tag>
              <el-tag size="small" :type="feedbackStatusTagType(fb.status)">
                {{ fb.status_label }}
              </el-tag>
            </div>
            <span class="item-time">{{ formatRelativeTime(fb.created_at) }}</span>
          </div>
          <div class="item-title">{{ fb.title }}</div>
          <div class="item-content">{{ fb.content }}</div>
          <div v-if="fb.handler_reply" class="item-reply-preview">
            <el-icon><ChatRound /></el-icon>
            <span>{{ fb.handler_name }}回复：{{ fb.handler_reply.substring(0, 50) }}...</span>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <!-- 提交反馈对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="提交新反馈"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="80px"
      >
        <el-form-item label="类型" prop="feedback_type">
          <el-select v-model="createForm.feedback_type" placeholder="请选择反馈类型" style="width: 100%">
            <el-option
              v-for="opt in FEEDBACK_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input
            v-model="createForm.title"
            placeholder="请输入反馈标题（最多200字）"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input
            v-model="createForm.content"
            type="textarea"
            :rows="5"
            placeholder="请详细描述您的反馈内容..."
            maxlength="5000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitFeedback">
          提交反馈
        </el-button>
      </template>
    </el-dialog>

    <!-- 反馈详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="反馈详情"
      width="650px"
    >
      <template v-if="currentFeedback">
        <div class="detail-header">
          <div class="detail-tags">
            <el-tag size="small" :color="getTypeColor(currentFeedback.feedback_type)" effect="light">
              {{ currentFeedback.feedback_type_label }}
            </el-tag>
            <el-tag size="small" :type="feedbackStatusTagType(currentFeedback.status)">
              {{ currentFeedback.status_label }}
            </el-tag>
          </div>
          <span class="detail-time">{{ formatRelativeTime(currentFeedback.created_at) }}</span>
        </div>
        <h3 class="detail-title">{{ currentFeedback.title }}</h3>
        <div class="detail-content">{{ currentFeedback.content }}</div>

        <!-- 回复区域 -->
        <div v-if="currentFeedback.handler_reply" class="reply-section">
          <div class="reply-header">
            <el-icon><ChatRound /></el-icon>
            <span class="reply-handler">{{ currentFeedback.handler_name }} 的回复</span>
            <span v-if="currentFeedback.handled_at" class="reply-time">
              {{ formatRelativeTime(currentFeedback.handled_at) }}
            </span>
          </div>
          <div class="reply-content">{{ currentFeedback.handler_reply }}</div>
        </div>
        <div v-else class="no-reply">
          <el-icon><Clock /></el-icon>
          <span>反馈正在处理中，请耐心等待老师回复</span>
        </div>

        <!-- 血缘追踪信息 -->
        <div v-if="currentFeedback.source_context" class="source-trace">
          <el-divider content-position="left">
            <span class="trace-label">
              <el-icon><InfoFilled /></el-icon>
              操作溯源
            </span>
          </el-divider>
          <div class="trace-info">
            <span>渠道：{{ currentFeedback.source_context.channel || '--' }}</span>
            <span>IP：{{ currentFeedback.source_context.client_ip || '--' }}</span>
            <span>时间：{{ currentFeedback.created_at }}</span>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  Plus,
  Refresh,
  ChatRound,
  Clock,
  InfoFilled,
} from '@element-plus/icons-vue'
import {
  listFeedbacks,
  createFeedback,
  feedbackStatusTagType,
  formatRelativeTime,
  FEEDBACK_TYPE_OPTIONS,
  FEEDBACK_STATUS_OPTIONS,
  FEEDBACK_TYPE_META,
  type FeedbackItem,
  type FeedbackType,
  type FeedbackStatus,
} from '@/api/parent_portal'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const loading = ref(false)
const submitting = ref(false)
const feedbacks = ref<FeedbackItem[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20

const filterType = ref<FeedbackType | undefined>(undefined)
const filterStatus = ref<FeedbackStatus | undefined>(undefined)

const showCreateDialog = ref(false)
const showDetailDialog = ref(false)
const currentFeedback = ref<FeedbackItem | null>(null)

const createFormRef = ref<FormInstance>()
const createForm = reactive({
  feedback_type: '' as FeedbackType | '',
  title: '',
  content: '',
})

const createRules: FormRules = {
  feedback_type: [{ required: true, message: '请选择反馈类型', trigger: 'change' }],
  title: [{ required: true, message: '请输入反馈标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入反馈内容', trigger: 'blur' }],
}

function getTypeColor(type: FeedbackType): string {
  return FEEDBACK_TYPE_META[type]?.color || '#909399'
}

async function fetchFeedbacks() {
  loading.value = true
  try {
    const res = await listFeedbacks({
      feedback_type: filterType.value || undefined,
      status: filterStatus.value || undefined,
      offset: (currentPage.value - 1) * pageSize,
      limit: pageSize,
    })
    feedbacks.value = res.items
    total.value = res.total
  } catch {
    ElMessage.error('反馈数据加载失败，请稍后刷新重试')
  } finally {
    loading.value = false
  }
}

function onPageChange(page: number) {
  currentPage.value = page
  fetchFeedbacks()
}

function openDetail(fb: FeedbackItem) {
  currentFeedback.value = fb
  showDetailDialog.value = true
}

async function submitFeedback() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      // 获取绑定的学生ID — 必须有绑定才能提交反馈
      const studentId = (userStore.userInfo as any)?.bound_student_id
      if (!studentId) {
        ElMessage.warning('您的账号未绑定学生，无法提交反馈，请联系班主任')
        submitting.value = false
        return
      }
      const result = await createFeedback({
        student_id: studentId,
        feedback_type: createForm.feedback_type as FeedbackType,
        title: createForm.title,
        content: createForm.content,
      })

      ElMessage.success('反馈已提交，班主任将尽快回复')
      showCreateDialog.value = false

      // 重置表单
      createForm.feedback_type = ''
      createForm.title = ''
      createForm.content = ''

      // 刷新列表
      fetchFeedbacks()
    } catch {
      // 错误已由 axios 拦截器处理
    } finally {
      submitting.value = false
    }
  })
}

onMounted(() => {
  fetchFeedbacks()
})
</script>

<style scoped>
.parent-feedback {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.create-btn {
  height: 40px;
}

.filter-card {
  margin-bottom: 16px;
}

.filter-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.list-card {
  min-height: 400px;
}

.loading-state {
  padding: 20px;
}

.empty-state {
  padding: 40px 0;
}

.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feedback-item {
  padding: 16px 20px;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.feedback-item:hover {
  background: #ecf5ff;
  border-color: #409eff;
}

.item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.item-tags {
  display: flex;
  gap: 8px;
}

.item-time {
  font-size: 12px;
  color: #909399;
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.item-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.item-reply-preview {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(103, 194, 58, 0.08);
  border-radius: 6px;
  font-size: 12px;
  color: #67c23a;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* 详情对话框 */
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.detail-tags {
  display: flex;
  gap: 8px;
}

.detail-time {
  font-size: 12px;
  color: #909399;
}

.detail-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 12px 0;
}

.detail-content {
  font-size: 14px;
  color: #606266;
  line-height: 1.7;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 16px;
}

.reply-section {
  padding: 16px;
  background: rgba(64, 158, 255, 0.06);
  border-radius: 8px;
  border-left: 3px solid #409eff;
}

.reply-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.reply-handler {
  font-size: 14px;
  font-weight: 600;
  color: #409eff;
}

.reply-time {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
}

.reply-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.7;
}

.no-reply {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: rgba(230, 162, 60, 0.06);
  border-radius: 8px;
  font-size: 14px;
  color: #e6a23c;
}

.source-trace {
  margin-top: 16px;
}

.trace-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}

.trace-info {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #909399;
}
</style>
