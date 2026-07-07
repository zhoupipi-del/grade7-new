<template>
  <div class="rdi-radar-container">
    <el-row :gutter="20">
      <!-- ═══ 左侧：风险筛查列表 ═══ -->
      <el-col :span="11">
        <el-card class="box-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="title">RDI 风险学生筛查 (多租户行级隔离)</span>
              <el-tag type="danger" effect="dark">实时更新</el-tag>
            </div>
          </template>

          <el-table
            :data="tableData"
            v-loading="loading"
            highlight-current-row
            @current-change="handleStudentSelect"
            row-key="student_id"
            style="width: 100%"
            height="calc(100vh - 200px)"
          >
            <el-table-column prop="name" label="姓名" width="100" fixed />
            <el-table-column prop="class_name" label="班级" width="100" />
            <el-table-column prop="rdi_score" label="RDI 总分" width="110" sortable>
              <template #default="scope">
                <span class="score-text">{{ scope.row.rdi_score.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_level" label="风控等级" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.risk_level === '干预' ? 'danger' : 'warning'">
                  {{ scope.row.risk_level }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- ═══ 右侧：三维交叉诊断面板 ═══ -->
      <el-col :span="13">
        <el-card v-if="selectedStudent" class="box-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="student-title">⚡ {{ selectedStudent.name }} — 深度立体诊断</span>
              <el-button type="primary" size="small" @click="goPrescription(selectedStudent)">
                查看 AI 处方
              </el-button>
            </div>
          </template>

          <div class="charts-pane">
            <!-- 维度 1: 三维偏离度雷达 -->
            <div class="chart-box">
              <div class="chart-title">RDI 三维偏离度立体图 (瞬时偏离风险)</div>
              <div ref="radarChartRef" class="echart-dom"></div>
            </div>

            <el-divider />

            <!-- 维度 2: EWMA 趋势演进 -->
            <div class="chart-box">
              <div class="chart-title">EWMA 风险演进趋势 (纵向时序演进)</div>
              <div ref="trendChartRef" class="echart-dom"></div>
            </div>
          </div>
        </el-card>

        <el-empty
          v-else
          description="请在左侧点击选择一名学生，查看三维数据合流深度诊断"
          class="empty-holder"
        />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { getHighRiskStudents, type StudentRiskRecord } from '@/api/rdi'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const tableData = ref<StudentRiskRecord[]>([])
const selectedStudent = ref<StudentRiskRecord | null>(null)

// ECharts DOM 引用
const radarChartRef = ref<HTMLDivElement | null>(null)
const trendChartRef = ref<HTMLDivElement | null>(null)

// ECharts 实例 (ReturnType 确保类型与 echarts.init 返回值一致)
let radarChartInstance: ReturnType<typeof echarts.init> | null = null
let trendChartInstance: ReturnType<typeof echarts.init> | null = null

// ─── 加载风险数据 ───────────────────────────────────────────────

const loadRiskData = async () => {
  loading.value = true
  try {
    const params: { class_id?: number } = {}
    // 角色数据隔离: 班主任自动限定本班
    if (userStore.currentRole === 'CLASS_TEACHER' && userStore.userInfo?.class_id) {
      params.class_id = userStore.userInfo.class_id
    }
    tableData.value = await getHighRiskStudents(params)
    // 默认选中第一条开始诊断
    if (tableData.value.length > 0) {
      handleStudentSelect(tableData.value[0])
    }
  } catch (err) {
    console.error('[RDI] load failed', err)
    ElMessage.error('无法加载风控雷达数据')
  } finally {
    loading.value = false
  }
}

// ─── 学生选中联动 ───────────────────────────────────────────────

const handleStudentSelect = (val: StudentRiskRecord | null) => {
  if (!val) return
  selectedStudent.value = val

  // 必须在 DOM 渲染后初始化/更新图表
  nextTick(() => {
    initRadarChart(val)
    initTrendChart(val)
  })
}

// ─── 渲染三维偏离度雷达图 ───────────────────────────────────────

const initRadarChart = (student: StudentRiskRecord) => {
  if (!radarChartRef.value) return
  if (!radarChartInstance) {
    radarChartInstance = echarts.init(radarChartRef.value)
  }

  // 根据风险等级动态配色: 干预→红, 预警→橙
  const isIntervention = student.risk_level === '干预'
  const areaColor = isIntervention ? 'rgba(245, 108, 108, 0.3)' : 'rgba(230, 162, 60, 0.3)'
  const lineColor = isIntervention ? '#f56c6c' : '#e6a23c'

  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const vals = params.value
        return `
          <div style="font-weight:600;margin-bottom:4px">${student.name}</div>
          <div>行为偏离: ${vals[0]?.toFixed(2)}σ</div>
          <div>考勤偏离: ${vals[1]?.toFixed(2)}σ</div>
          <div>学业偏离: ${vals[2]?.toFixed(2)}σ</div>
        `
      },
    },
    radar: {
      indicator: [
        { name: '行为偏离度 (Behavior)', max: 10 },
        { name: '考勤偏离度 (Attendance)', max: 10 },
        { name: '学业下滑度 (Academic)', max: 10 }
      ],
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      splitLine: { lineStyle: { color: '#e4e7ed' } },
      axisName: { color: '#606266', fontSize: 12 },
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [
            student.diagnosis.behavior_deviation,
            student.diagnosis.attendance_deviation,
            student.diagnosis.score_deviation
          ],
          name: student.name,
          areaStyle: { color: areaColor },
          lineStyle: { color: lineColor, width: 2 },
          itemStyle: { color: lineColor },
        }
      ]
    }]
  }
  radarChartInstance.setOption(option, true)
}

// ─── 渲染 EWMA 演进趋势 ─────────────────────────────────────────

const initTrendChart = (student: StudentRiskRecord) => {
  if (!trendChartRef.value) return
  if (!trendChartInstance) {
    trendChartInstance = echarts.init(trendChartRef.value)
  }

  const option: any = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        return `<div style="font-weight:600">${student.name}</div>${p.name}: RDI ${p.value}`
      },
    },
    xAxis: {
      type: 'category',
      data: student.diagnosis.scan_dates,
      axisLine: { lineStyle: { color: '#909399' } },
      axisLabel: { color: '#606266' },
    },
    yAxis: {
      type: 'value',
      name: 'RDI指数',
      splitLine: { lineStyle: { type: 'dashed', color: '#e4e7ed' } },
      axisLabel: { color: '#606266' },
    },
    series: [{
      data: student.diagnosis.ewma_trend,
      type: 'line',
      smooth: true,
      lineStyle: { color: '#409eff', width: 3 },
      itemStyle: { color: '#409eff' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64, 158, 255, 0.2)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0)' }
          ]
        }
      },
      markPoint: {
        data: [{ type: 'max', name: '峰值' }],
        symbolSize: 40,
      },
    }]
  }
  trendChartInstance.setOption(option, true)
}

// ─── 路由闭环: 跳转 AI 处方 ─────────────────────────────────────

const goPrescription = (student: StudentRiskRecord) => {
  router.push(`/ai-prescription?warning_id=${student.warning_id}&student_id=${student.student_id}`)
}

// ─── 自适应视窗缩放 ─────────────────────────────────────────────

const handleResize = () => {
  radarChartInstance?.resize()
  trendChartInstance?.resize()
}

// ─── 生命周期 ───────────────────────────────────────────────────

onMounted(() => {
  loadRiskData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  radarChartInstance?.dispose()
  trendChartInstance?.dispose()
  radarChartInstance = null
  trendChartInstance = null
})
</script>

<style scoped>
.rdi-radar-container {
  background-color: #f5f7fa;
  min-height: calc(100vh - 100px);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: bold;
  color: #303133;
}
.student-title {
  font-weight: bold;
  color: #e6a23c;
}
.score-text {
  font-family: 'Courier New', Courier, monospace;
  font-weight: bold;
  color: #f56c6c;
}
.charts-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chart-box {
  padding: 10px 0;
}
.chart-title {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 15px;
  padding-left: 8px;
  border-left: 4px solid #409eff;
}
.echart-dom {
  width: 100%;
  height: 220px;
}
.empty-holder {
  background-color: #ffffff;
  border: 1px solid #e6ebf5;
  border-radius: 4px;
  height: calc(100vh - 200px);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
