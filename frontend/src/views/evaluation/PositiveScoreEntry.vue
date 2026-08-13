<template>
  <div class="positive-score-entry">
    <!-- ════════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Plus /></el-icon>
          正向加分 · 极简登记
        </h2>
        <span class="page-subtitle">课堂表现 · 帮助同学 · 劳动实践 · 明显进步 · 集体贡献</span>
      </div>
      <div class="header-right">
        <el-tag type="success" effect="plain" size="small">
          15 秒 · 可信记录
        </el-tag>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 极简表扬表单（QuickPraise）             -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="entry-card">
      <template #header>
        <span class="card-title-text">
          <el-icon><EditPen /></el-icon> 登记正向表扬
        </span>
      </template>

      <!-- 提交成功视图 -->
      <div v-if="praiseStep === 'success' && praiseResult" class="praise-success">
        <el-icon class="praise-check"><CircleCheckFilled /></el-icon>
        <div class="praise-success-title">表扬成功</div>
        <div class="praise-success-student">{{ praiseResult.student_name }}</div>
        <div class="praise-success-detail">
          {{ praiseResult.praise_label }} <span class="score-tag">+{{ praiseResult.score }} 分</span>
        </div>
        <div class="praise-success-monthly">
          本月可信表扬记录：<b>{{ praiseResult.monthly_praise_count }}</b>
        </div>
        <div class="praise-success-actions">
          <el-button type="primary" @click="continuePraise">继续表扬</el-button>
          <el-button @click="praiseStep = 'form'">完成</el-button>
        </div>
      </div>

      <!-- 表单视图 -->
      <el-form
        v-else
        ref="praiseFormRef"
        :model="formData"
        :rules="formRules"
        label-width="0"
        size="large"
      >
        <!-- 选择学生 -->
        <el-form-item prop="student_id">
          <el-select
            v-model="formData.student_id"
            placeholder="① 选择学生"
            filterable
            remote
            :remote-method="searchStudents"
            :loading="studentsLoading"
            style="width: 100%"
            size="large"
          >
            <el-option
              v-for="s in studentOptions"
              :key="s.id"
              :label="`${s.name} (${s.student_no || s.id}) · ${s.class_name || ''}`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>

        <!-- 表扬类型 -->
        <el-form-item prop="praise_type">
          <el-radio-group v-model="formData.praise_type" class="praise-type-group">
            <el-radio-button
              v-for="t in PRAISE_TYPES"
              :key="t.value"
              :value="t.value"
            >
              {{ t.label }}
            </el-radio-button>
          </el-radio-group>
          <div class="praise-hint">② 选择表扬类型（分值为系统统一默认，无需手动填写）</div>
        </el-form-item>

        <!-- 备注（可选） -->
        <el-form-item prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="③ 备注（可选）：简单记一句值得肯定的事..."
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <!-- 提交 -->
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="submit-btn"
            :loading="submitLoading"
            :disabled="!formData.student_id || !formData.praise_type"
            @click="submitPraise"
          >
            <el-icon><Check /></el-icon>
            提交表扬
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- 本月表扬速览                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="recent-records-card">
      <template #header>
        <span class="card-title-text">
          <el-icon><List /></el-icon> 表扬记录（仅可信 teacher_manual）
        </span>
      </template>

      <el-table
        :data="recentRecords"
        v-loading="recordsLoading"
        style="width: 100%"
        size="default"
        stripe
      >
        <el-table-column prop="student_name" label="学生姓名" width="120" />
        <el-table-column prop="indicator_name" label="表扬类型" width="150" />
        <el-table-column prop="score" label="分值" width="90" align="center">
          <template #default="{ row }">
            <el-tag type="success" size="small">+{{ row.score }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="备注" min-width="200" />
        <el-table-column prop="incident_date" label="日期" width="120" />
      </el-table>

      <el-empty
        v-if="recentRecords.length === 0 && !recordsLoading"
        description="暂无可信表扬记录"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * PositiveScoreEntry.vue — 正向加分 · 极简登记（Step6 QuickPraise）
 *
 * 15 秒完成一条可信正向记录：
 *   选学生 → 选表扬类型 → 备注(可选) → 提交
 * 服务端锁死（/evaluation/quick-praise）：
 *   source=teacher_manual / indicator+score 由表扬类型映射 / class+grade 反查
 *
 * 对应后端 API:
 *  - GET  /behavior/quick-register/students   — 按角色可见范围选学生（复用）
 *  - POST /evaluation/quick-praise           — 极简正向表扬
 *  - GET  /evaluation/students/{id}/logs     — 最近记录
 */

import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, EditPen, List, Check, CircleCheckFilled } from '@element-plus/icons-vue'
import request from '@/api/request'
import { getQuickRegisterStudents } from '@/api/behavior'
import {
  type PraiseType,
  type QuickPraiseOut,
  quickPraise,
  getScoreLogs,
} from '@/api/evaluation'

const PRAISE_TYPES: Array<{ value: PraiseType; label: string }> = [
  { value: 'class_performance', label: '课堂表现' },
  { value: 'help_others', label: '帮助同学' },
  { value: 'labor', label: '劳动实践' },
  { value: 'progress', label: '明显进步' },
  { value: 'collective', label: '集体贡献' },
  { value: 'other', label: '其他' },
]

const praiseFormRef = ref()
const submitLoading = ref(false)
const studentsLoading = ref(false)
const recordsLoading = ref(false)

const praiseStep = ref<'form' | 'success'>('form')
const praiseResult = ref<QuickPraiseOut | null>(null)

const formData = reactive({
  student_id: undefined as number | undefined,
  praise_type: undefined as PraiseType | undefined,
  description: '',
})

const formRules = {
  student_id: [{ required: true, message: '请选择学生', trigger: 'change' }],
  praise_type: [{ required: true, message: '请选择表扬类型', trigger: 'change' }],
}

const studentOptions = ref<Array<{ id: number; name: string; student_no: string; class_name: string }>>([])
const recentRecords = ref<Array<Record<string, any>>>([])

onMounted(() => {
  loadStudents()
  loadRecentRecords()
})

async function loadStudents() {
  studentsLoading.value = true
  try {
    // 复用 behavior QuickRegister 学生选择器：按角色 scope 返回（班主任=本班，组长=授权年级）
    const list: any[] = await getQuickRegisterStudents({})
    studentOptions.value = (list || []).map((s: any) => ({
      id: s.id,
      name: s.name,
      student_no: s.student_no || '',
      class_name: s.class_name || '',
    }))
  } catch (err: any) {
    ElMessage.error(`加载学生失败: ${err.message || err}`)
  } finally {
    studentsLoading.value = false
  }
}

async function searchStudents(query: string) {
  if (!query.trim()) {
    loadStudents()
    return
  }
  studentsLoading.value = true
  try {
    const list: any[] = await getQuickRegisterStudents({ keyword: query.trim() })
    studentOptions.value = (list || []).map((s: any) => ({
      id: s.id,
      name: s.name,
      student_no: s.student_no || '',
      class_name: s.class_name || '',
    }))
  } catch (err: any) {
    ElMessage.error(`搜索学生失败: ${err.message || err}`)
  } finally {
    studentsLoading.value = false
  }
}

async function loadRecentRecords() {
  if (!formData.student_id) {
    recentRecords.value = []
    return
  }
  recordsLoading.value = true
  try {
    const data: any = await getScoreLogs(formData.student_id, 1, 20)
    const items = data?.items ?? data ?? []
    // 只展示老师表扬（source 后端已过滤；此处按 scorer_type=teacher 粗筛）
    recentRecords.value = (items as any[]).filter((log: any) => log.scorer_type === 'teacher')
  } catch (err: any) {
    ElMessage.error(`加载记录失败: ${err.message || err}`)
  } finally {
    recordsLoading.value = false
  }
}

async function submitPraise() {
  try {
    await praiseFormRef.value?.validate()
  } catch {
    return
  }
  submitLoading.value = true
  try {
    const res = await quickPraise({
      student_id: formData.student_id!,
      praise_type: formData.praise_type!,
      description: formData.description?.trim() || undefined,
    })
    praiseResult.value = res
    praiseStep.value = 'success'
    loadRecentRecords()
  } catch (err: any) {
    ElMessage.error(`提交失败: ${err.message || err}`)
  } finally {
    submitLoading.value = false
  }
}

function continuePraise() {
  praiseStep.value = 'form'
  formData.student_id = undefined
  formData.praise_type = undefined
  formData.description = ''
  praiseFormRef.value?.resetFields()
  loadStudents()
}

// 简单请求封装（未使用 request 直调，保持与既有组件一致）
void request
</script>

<style scoped>
.positive-score-entry {
  padding: 16px;
  background: #f5f7fa;
  min-height: calc(100vh - 64px);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.page-subtitle {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}

.entry-card,
.recent-records-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.card-title-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
}

.praise-type-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.praise-hint {
  width: 100%;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.submit-btn {
  width: 100%;
}

/* 成功视图 */
.praise-success {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 0 12px;
  text-align: center;
}

.praise-check {
  font-size: 56px;
  color: #67c23a;
  margin-bottom: 8px;
}

.praise-success-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.praise-success-student {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.praise-success-detail {
  margin-top: 4px;
  font-size: 16px;
  color: #606266;
}

.score-tag {
  color: #67c23a;
  font-weight: 600;
}

.praise-success-monthly {
  margin-top: 12px;
  font-size: 14px;
  color: #909399;
}

.praise-success-monthly b {
  color: #67c23a;
  font-size: 18px;
}

.praise-success-actions {
  margin-top: 20px;
}
</style>
