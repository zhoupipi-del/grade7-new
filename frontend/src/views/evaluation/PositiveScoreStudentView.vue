<template>
  <div class="positive-score-student-view">
    <!-- ════════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ════════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Trophy /></el-icon>
          我的正能量档案
        </h2>
        <span class="page-subtitle">记录成长 · 见证进步 · 传递正能量</span>
      </div>
      <div class="header-right">
        <el-tag type="success" effect="dark" size="large">
          正能量积分: {{ totalPositiveScore }}
        </el-tag>
      </div>
    </div>

    <!-- ════════════════════════════════════════ -->
    <!-- 五维雷达图 + 统计卡片                   -->
    <!-- ════════════════════════════════════════ -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="16">
        <el-card shadow="never" class="radar-card">
          <template #header>
            <span class="card-title-text">
              <el-icon><DataAnalysis /></el-icon> 五维素质雷达图
            </span>
          </template>
          <div ref="radarChartRef" class="radar-chart-container"></div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="stats-card">
          <template #header>
            <span class="card-title-text">
              <el-icon><TrendCharts /></el-icon> 正能量统计
            </span>
          </template>

          <div class="stat-item">
            <div class="stat-label">总加分次数</div>
            <div class="stat-value">{{ positiveRecords.length }}</div>
          </div>

          <div class="stat-item">
            <div class="stat-label">总加分分数</div>
            <div class="stat-value positive">{{ totalPositiveScore }}</div>
          </div>

          <div class="stat-item">
            <div class="stat-label">班级排名</div>
            <div class="stat-value" :class="rankClass">{{ classRanking }}</div>
          </div>

          <div class="stat-item">
            <div class="stat-label">年级排名</div>
            <div class="stat-value" :class="rankClass">{{ gradeRanking }}</div>
          </div>

          <el-divider />

          <div class="dimension-scores">
            <div class="dim-title">各维度加分</div>
            <div
              v-for="dim in dimensionScores"
              :key="dim.dimension"
              class="dim-row"
            >
              <span class="dim-label">{{ dimensionLabel(dim.dimension) }}</span>
              <el-progress
                :percentage="dim.percentage"
                :color="dim.color"
                :stroke-width="12"
                :text-inside="true"
                :format="() => `${dim.score}分`"
              />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ════════════════════════════════════════ -->
    <!-- 正向加分记录表格                       -->
    <!-- ════════════════════════════════════════ -->
    <el-card shadow="never" class="records-card">
      <template #header>
        <div class="card-header-with-action">
          <span class="card-title-text">
            <el-icon><List /></el-icon> 正向加分记录
          </span>
          <el-button
            type="primary"
            size="small"
            @click="loadPositiveRecords"
          >
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="positiveRecords"
        v-loading="recordsLoading"
        style="width: 100%"
        size="default"
        stripe
        empty-text="暂无正向加分记录"
      >
        <el-table-column prop="created_at" label="加分时间" width="180" />
        <el-table-column prop="indicator_name" label="加分项目" width="150" />
        <el-table-column prop="dimension" label="所属维度" width="120" align="center">
          <template #default="{ row }">
            <el-tag :color="dimensionColor(row.dimension)" size="small">
              {{ dimensionLabel(row.dimension) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="change_amount" label="加分分数" width="100" align="center">
          <template #default="{ row }">
            <span class="positive-score">+{{ row.change_amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="加分说明" min-width="200" />
        <el-table-column prop="scorer_type" label="录入人" width="120" align="center">
          <template #default="{ row }">
            {{ scorerTypeLabel(row.scorer_type) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="totalRecords"
          layout="total, sizes, prev, pager, next"
          @size-change="loadPositiveRecords"
          @current-change="loadPositiveRecords"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * PositiveScoreStudentView.vue — 学生端正向加分查看页面
 *
 * 功能:
 *  1. 显示学生的正向加分记录（加分指标、分数、时间、备注）
 *  2. 显示五维雷达图（含正向加分后的最新分数）
 *  3. 显示班级/年级排名变化
 *
 * 对应后端 API:
 *  - GET /api/v1/evaluation/students/{id}/scores      — 学生五维分+总分
 *  - GET /api/v1/evaluation/students/{id}/logs        — 评分流水（过滤 change_amount > 0）
 *  - GET /api/v1/evaluation/classes/{class_id}/ranking — 班级排名
 */

import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Trophy, DataAnalysis, TrendCharts, List, Refresh,
} from '@element-plus/icons-vue'
import request from '@/api/request'
import {
  type EvalDimension,
  type ScoreLogItem,
  getStudentScores,
  getScoreLogs,
  dimensionLabel,
  dimensionColor,
} from '@/api/evaluation'

// ════════════════════════════════════════
// ECharts
// ════════════════════════════════════════

let echarts: any = null

// ════════════════════════════════════════
// 响应式状态
// ════════════════════════════════════════

const radarChartRef = ref<HTMLElement>()
const recordsLoading = ref(false)

const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)

const positiveRecords = ref<ScoreLogItem[]>([])

const studentScores = ref<{
  moral_score: number
  academic_score: number
  health_score: number
  art_score: number
  social_score: number
  total_score: number
} | null>(null)

const classRanking = ref<number>(0)
const gradeRanking = ref<number>(0)

// ════════════════════════════════════════
// 计算属性
// ════════════════════════════════════════

const totalPositiveScore = computed(() => {
  return positiveRecords.value.reduce((sum, record) => sum + (record.change_amount || 0), 0)
})

const dimensionScores = computed(() => {
  const dimMap: Record<string, number> = {
    moral: 0,
    academic: 0,
    health: 0,
    art: 0,
    social: 0,
  }

  for (const record of positiveRecords.value) {
    if (record.dimension && dimMap[record.dimension] !== undefined) {
      dimMap[record.dimension] += record.change_amount || 0
    }
  }

  const maxScore = Math.max(...Object.values(dimMap), 1)

  return Object.entries(dimMap).map(([dim, score]) => ({
    dimension: dim as EvalDimension,
    score,
    percentage: Math.round((score / maxScore) * 100),
    color: dimensionColor(dim as EvalDimension),
  }))
})

const rankClass = computed(() => {
  if (classRanking.value <= 3) return 'top-rank'
  if (classRanking.value <= 10) return 'good-rank'
  return 'normal-rank'
})

// ════════════════════════════════════════
// 生命周期
// ════════════════════════════════════════

onMounted(async () => {
  await loadStudentData()
  await loadPositiveRecords()
  initRadarChart()
})

// ════════════════════════════════════════
// 数据加载
// ════════════════════════════════════════

async function loadStudentData() {
  try {
    // TODO: 获取当前登录学生的 ID（从 JWT 或 store）
    const studentId = 1 // 临时硬编码，实际应从用户状态获取

    // 加载学生五维分数
    const scores = await getStudentScores(studentId)
    studentScores.value = scores

    // 加载排名（需要 class_id，暂时跳过）
    // const ranking = await getClassRanking(classId)
    // classRanking.value = ranking.findIndex(r => r.student_id === studentId) + 1
  } catch (err: any) {
    ElMessage.error(`加载学生数据失败: ${err.message || err}`)
  }
}

async function loadPositiveRecords() {
  try {
    // TODO: 获取当前登录学生的 ID
    const studentId = 1 // 临时硬编码

    recordsLoading.value = true
    const data = await getScoreLogs(studentId, currentPage.value, pageSize.value)

    // 筛选出正向加分记录（score > 0）
    positiveRecords.value = data.items.filter(log => log.change_amount > 0)
    totalRecords.value = data.total
  } catch (err: any) {
    ElMessage.error(`加载加分记录失败: ${err.message || err}`)
  } finally {
    recordsLoading.value = false
  }
}

// ════════════════════════════════════════
// 雷达图
// ════════════════════════════════════════

async function initRadarChart() {
  if (!radarChartRef.value) return

  try {
    // 动态导入 ECharts
    const echartsModule = await import('echarts')
    echarts = echartsModule.init(radarChartRef.value)

    updateRadarChart()
  } catch (err) {
    console.error('Failed to load ECharts:', err)
  }
}

function updateRadarChart() {
  if (!echarts || !studentScores.value) return

  const scores = studentScores.value

  const option = {
    title: {
      text: '五维素质雷达图',
      left: 'center',
    },
    tooltip: {},
    radar: {
      indicator: [
        { name: '道德品质', max: 100 },
        { name: '学业水平', max: 100 },
        { name: '身心健康', max: 100 },
        { name: '艺术素养', max: 100 },
        { name: '社会实践', max: 100 },
      ],
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [
              scores.moral_score,
              scores.academic_score,
              scores.health_score,
              scores.art_score,
              scores.social_score,
            ],
            name: '当前分数',
            areaStyle: {
              opacity: 0.3,
            },
          },
        ],
      },
    ],
  }

  echarts.setOption(option)
}

// ════════════════════════════════════════
// 辅助函数
// ════════════════════════════════════════

function scorerTypeLabel(scorerType: string): string {
  const map: Record<string, string> = {
    teacher: '教师',
    self: '自评',
    peer: '互评',
    parent: '家长',
    ms_admin: '管理员',
  }
  return map[scorerType] || scorerType
}
</script>

<style scoped>
.positive-score-student-view {
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

.stats-row {
  margin-bottom: 16px;
}

.radar-card,
.stats-card,
.records-card {
  border-radius: 8px;
}

.card-title-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
}

.card-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.radar-chart-container {
  width: 100%;
  height: 400px;
}

.stat-item {
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.stat-value.positive {
  color: #67c23a;
}

.stat-value.top-rank {
  color: #f56c6c;
}

.stat-value.good-rank {
  color: #e6a23c;
}

.stat-value.normal-rank {
  color: #909399;
}

.dimension-scores {
  margin-top: 16px;
}

.dim-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.dim-row {
  margin-bottom: 8px;
}

.dim-label {
  display: block;
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
}

.positive-score {
  font-size: 16px;
  font-weight: 600;
  color: #67c23a;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
