<template>
  <div class="positive-score-entry">
    <!-- ════════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Plus /></el-icon>
          正向加分录入
        </h2>
        <span class="page-subtitle">品德之星 · 助人为乐 · 志愿服务 · 劳动实践</span>
      </div>
      <div class="header-right">
        <el-tag type="success" effect="plain" size="small">
          奖惩并举 · 激励向上
        </el-tag>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 加分录入表单                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="entry-card">
      <template #header>
        <span class="card-title-text">
          <el-icon><EditPen /></el-icon> 录入正向加分
        </span>
      </template>

      <el-form
        ref="scoreFormRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
        label-position="right"
        size="default"
      >
        <!-- 选择学生 -->
        <el-form-item label="选择学生" prop="student_id">
          <el-select
            v-model="formData.student_id"
            placeholder="请选择学生"
            filterable
            remote
            :remote-method="searchStudents"
            :loading="studentsLoading"
            style="width: 100%"
            @change="onStudentChange"
          >
            <el-option
              v-for="s in studentOptions"
              :key="s.id"
              :label="`${s.name} (${s.student_no}) · ${s.class_name}`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>

        <!-- 选择加分指标 -->
        <el-form-item label="加分指标" prop="indicator_id">
          <el-select
            v-model="formData.indicator_id"
            placeholder="请选择加分指标"
            style="width: 100%"
            @change="onIndicatorChange"
          >
            <el-option-group
              v-for="group in positiveIndicatorsGrouped"
              :key="group.dimension"
              :label="dimensionLabel(group.dimension)"
            >
              <el-option
                v-for="ind in group.indicators"
                :key="ind.id"
                :label="`${ind.name} (权重: ${ind.weight})`"
                :value="ind.id"
              />
            </el-option-group>
          </el-select>
        </el-form-item>

        <!-- 加分分数 -->
        <el-form-item label="加分分数" prop="score">
          <el-input-number
            v-model="formData.score"
            :min="1"
            :max="selectedIndicator?.max_score || 100"
            :step="1"
            style="width: 200px"
          />
          <span class="score-hint" v-if="selectedIndicator">
            满分: {{ selectedIndicator.max_score }} 分
          </span>
        </el-form-item>

        <!-- 备注说明 -->
        <el-form-item label="备注说明" prop="comment">
          <el-input
            v-model="formData.comment"
            type="textarea"
            :rows="3"
            placeholder="请输入加分原因或说明..."
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <!-- 提交按钮 -->
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="submitLoading"
            :disabled="!formData.student_id || !formData.indicator_id"
            @click="submitScore"
          >
            <el-icon><Check /></el-icon>
            提交加分
          </el-button>
          <el-button size="large" @click="resetForm">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ════════════════════════════════════════ -->
    <!-- 最近加分记录                           -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="recent-records-card">
      <template #header>
        <span class="card-title-text">
          <el-icon><List /></el-icon> 最近加分记录
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
        <el-table-column prop="indicator_name" label="加分指标" width="150" />
        <el-table-column prop="score" label="加分分数" width="100" align="center">
          <template #default="{ row }">
            <el-tag type="success" size="small">+{{ row.score }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="备注说明" min-width="200" />
        <el-table-column prop="created_at" label="录入时间" width="180" />
      </el-table>

      <el-empty
        v-if="recentRecords.length === 0 && !recordsLoading"
        description="暂无加分记录"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * PositiveScoreEntry.vue — 正向加分录入界面
 *
 * 功能:
 *  1. 选择学生（远程搜索）
 *  2. 选择正向加分指标（按维度分组）
 *  3. 录入加分分数
 *  4. 提交并查看最近记录
 *
 * 对应后端 API:
 *  - GET  /api/v1/evaluation/indicators      — 获取正向加分指标
 *  - POST /api/v1/evaluation/scores         — 提交加分记录
 *  - GET  /api/v1/evaluation/students/{id}/logs — 获取最近记录
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, EditPen, List, Check, Search,
} from '@element-plus/icons-vue'
import request from '@/api/request'
import { getClasses, getGrades, getStudents } from '@/api/classes'
import {
  type EvalDimension,
  type IndicatorItem,
  type ScoreLogItem,
  listIndicators,
  recordScore,
  getScoreLogs,
  dimensionLabel as getDimensionLabel,
} from '@/api/evaluation'

// ════════════════════════════════════════
// 响应式状态
// ════════════════════════════════════════

const scoreFormRef = ref()
const submitLoading = ref(false)
const studentsLoading = ref(false)
const recordsLoading = ref(false)

const formData = reactive({
  student_id: undefined as number | undefined,
  indicator_id: undefined as number | undefined,
  score: 5,
  comment: '',
})

const formRules = {
  student_id: [{ required: true, message: '请选择学生', trigger: 'change' }],
  indicator_id: [{ required: true, message: '请选择加分指标', trigger: 'change' }],
  score: [{ required: true, message: '请输入加分分数', trigger: 'blur' }],
}

const studentOptions = ref<Array<{ id: number; name: string; student_no: string; class_name: string; class_id?: number; grade_id?: number }>>([])
const selectedStudent = ref<{ id: number; name: string; student_no: string; class_name: string; class_id?: number; grade_id?: number } | null>(null)

const positiveIndicators = ref<Array<{ dimension: EvalDimension; item: IndicatorItem }>>([])
const selectedIndicator = ref<IndicatorItem | null>(null)

const recentRecords = ref<ScoreLogItem[]>([])

// ════════════════════════════════════════
// 计算属性
// ════════════════════════════════════════

const positiveIndicatorsGrouped = computed(() => {
  const groups: Array<{ dimension: EvalDimension; indicators: IndicatorItem[] }> = []
  const dimMap: Record<string, IndicatorItem[]> = {}

  for (const { dimension, item } of positiveIndicators.value) {
    if (!dimMap[dimension]) {
      dimMap[dimension] = []
    }
    dimMap[dimension].push(item)
  }

  for (const dim of Object.keys(dimMap) as EvalDimension[]) {
    groups.push({
      dimension: dim,
      indicators: dimMap[dim],
    })
  }

  return groups
})

// ════════════════════════════════════════
// 生命周期
// ════════════════════════════════════════

onMounted(() => {
  loadPositiveIndicators()
})

// ════════════════════════════════════════
// 数据加载
// ════════════════════════════════════════

async function loadPositiveIndicators() {
  try {
    const data = await listIndicators()
    // 筛选出正向加分指标（保留 dimension 信息）
    const positiveList: Array<{ dimension: EvalDimension; item: IndicatorItem }> = []
    for (const group of data) {
      for (const ind of group.indicators) {
        if (
          ind.name.includes('之星') ||
          ind.name.includes('助人') ||
          ind.name.includes('拾金') ||
          ind.name.includes('诚信') ||
          ind.name.includes('体育') ||
          ind.name.includes('文体') ||
          ind.name.includes('文艺') ||
          ind.name.includes('艺术') ||
          ind.name.includes('志愿') ||
          ind.name.includes('社区') ||
          ind.name.includes('公益') ||
          ind.name.includes('劳动')
        ) {
          positiveList.push({ dimension: group.dimension, item: ind })
        }
      }
    }
    positiveIndicators.value = positiveList
  } catch (err: any) {
    ElMessage.error(`加载加分指标失败: ${err.message || err}`)
  }
}

async function searchStudents(query: string) {
  if (!query.trim()) {
    studentOptions.value = []
    return
  }

  studentsLoading.value = true
  try {
    const res: any = await getStudents({ page: 1, page_size: 50 })
    const list = res?.items ?? (Array.isArray(res) ? res : [])
    // 搜索过滤（按姓名或学号）
    const kw = query.toLowerCase()
    const filtered = list.filter((s: any) =>
      s.name?.toLowerCase().includes(kw) ||
      s.student_no?.toLowerCase().includes(kw) ||
      s.student_number?.toLowerCase().includes(kw),
    )
    studentOptions.value = filtered.map((s: any) => ({
      id: s.id,
      name: s.name,
      student_no: s.student_no || s.student_number || '',
      class_name: s.class_name || '',
      class_id: s.class_id,
      grade_id: s.grade_id,
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
    const data = await getScoreLogs(formData.student_id, 1, 20)
    // 筛选出正向加分记录（change_amount > 0）
    recentRecords.value = data.items.filter(log => log.change_amount > 0)
  } catch (err: any) {
    ElMessage.error(`加载最近记录失败: ${err.message || err}`)
  } finally {
    recordsLoading.value = false
  }
}

// ════════════════════════════════════════
// 事件处理
// ════════════════════════════════════════

function onStudentChange(studentId: number) {
  selectedStudent.value = studentOptions.value.find(s => s.id === studentId) || null
  loadRecentRecords()
}

function onIndicatorChange(indicatorId: number) {
  const found = positiveIndicators.value.find(ind => ind.item.id === indicatorId)
  selectedIndicator.value = found?.item || null
  if (selectedIndicator.value) {
    formData.score = Math.min(5, selectedIndicator.value.max_score)
  }
}

async function submitScore() {
  // 表单验证
  try {
    await scoreFormRef.value?.validate()
  } catch {
    return
  }

  await ElMessageBox.confirm(
    `确认为学生「${selectedStudent.value?.name}」录入正向加分？\n\n` +
    `加分指标: ${selectedIndicator.value?.name}\n` +
    `加分分数: +${formData.score} 分\n` +
    `备注说明: ${formData.comment || '无'}`,
    '确认提交',
    {
      confirmButtonText: '确认提交',
      cancelButtonText: '取消',
      type: 'success',
    }
  )

  submitLoading.value = true
  try {
    // 从选中学生获取 class_id 和 grade_id（不再硬编码为1）
    const classId = selectedStudent.value?.['class_id']
    const gradeId = selectedStudent.value?.['grade_id']

    if (!classId || !gradeId) {
      ElMessage.warning('缺少班级/年级信息，请重新选择学生')
      submitLoading.value = false
      return
    }

    await recordScore({
      student_id: formData.student_id!,
      class_id: classId,
      grade_id: gradeId,
      indicator_id: formData.indicator_id!,
      score: formData.score,
      scorer_type: 'teacher',
      comment: formData.comment,
    })

    ElMessage.success(`成功为学生「${selectedStudent.value?.name}」录入正向加分 +${formData.score} 分`)
    resetForm()
    loadRecentRecords()
  } catch (err: any) {
    ElMessage.error(`提交失败: ${err.message || err}`)
  } finally {
    submitLoading.value = false
  }
}

function resetForm() {
  formData.student_id = undefined
  formData.indicator_id = undefined
  formData.score = 5
  formData.comment = ''
  selectedStudent.value = null
  selectedIndicator.value = null
  scoreFormRef.value?.resetFields()
}

function dimensionLabel(dim: string): string {
  return getDimensionLabel(dim)
}
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

.score-hint {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}
</style>
