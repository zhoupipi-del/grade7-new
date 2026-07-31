<template>
  <div class="instance-grid-wrapper">
    <!-- 控制栏 -->
    <el-card class="control-bar" shadow="never">
      <div class="control-row">
        <div class="control-left">
          <el-form :inline="true" size="default">
            <el-form-item label="班级">
              <el-select
                v-model="selectedClassId"
                filterable
                placeholder="选择班级"
                style="width: 160px"
                @change="onClassChange"
              >
                <el-option
                  v-for="c in classList"
                  :key="c.id"
                  :label="c.name"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="周次">
              <el-date-picker
                v-model="weekDate"
                type="week"
                format="YYYY 第 ww 周"
                value-format="YYYY-MM-DD"
                :clearable="false"
                style="width: 180px"
                @change="onWeekChange"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading" @click="fetchInstances">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button v-if="canAdjust" @click="toggleAdjustedOnly">
                {{ showAdjustedOnly ? '显示全部' : '仅看已变轨' }}
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="control-right">
          <el-tag v-if="adjustedCount > 0" type="warning" size="large" effect="dark">
            已变轨: {{ adjustedCount }} 节
          </el-tag>
          <el-tag v-else type="success" size="large" effect="plain">
            课表正常
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- 时空网格 -->
    <el-card class="grid-card" shadow="never" v-loading="loading">
      <template #header>
        <div class="grid-header">
          <span class="grid-title">
            {{ currentWeekLabel }}
          </span>
          <span class="grid-hint" v-if="canAdjust">
            双击课节格子进行变轨操作
          </span>
        </div>
      </template>

      <div v-if="instances.length > 0" class="timetable-grid">
        <!-- 表头：空角 + 7天 -->
        <div class="grid-cell grid-corner">节次</div>
        <div
          v-for="d in weekDays"
          :key="d.dateStr"
          class="grid-cell grid-day-header"
          :class="{ 'is-today': d.isToday }"
        >
          <div class="day-name">{{ d.label }}</div>
          <div class="day-date">{{ d.dateLabel }}</div>
        </div>

        <!-- 网格主体：8行(节) x 7列(天) -->
        <template v-for="period in 8" :key="'period-' + period">
          <!-- 左侧节次标签 -->
          <div class="grid-cell grid-period-label">
            <div class="period-num">第{{ period }}节</div>
            <div class="period-time">{{ periodTimes[period - 1] }}</div>
          </div>
          <!-- 7天格子 -->
          <div
            v-for="d in weekDays"
            :key="`cell-${period}-${d.dateStr}`"
            class="grid-cell grid-slot"
            :class="{
              'is-today-col': d.isToday,
              'is-empty': !getCell(period, d.dateStr),
              'is-adjusted': getCell(period, d.dateStr)?.is_adjusted,
            }"
            @dblclick="onCellDblClick(period, d.dateStr)"
          >
            <template v-if="getCell(period, d.dateStr)">
              <div class="slot-subject" :style="{ borderLeftColor: getSubjectColor(getCell(period, d.dateStr)!.subject_id) }">
                {{ getSubjectName(getCell(period, d.dateStr)!.subject_id) }}
              </div>
              <div class="slot-teacher">
                <el-icon size="11"><User /></el-icon>
                {{ getTeacherName(getCell(period, d.dateStr)!.teacher_id) }}
              </div>
              <div v-if="getCell(period, d.dateStr)!.is_adjusted" class="slot-adjusted-badge">
                <el-icon size="10"><WarningFilled /></el-icon>
                已变轨
              </div>
            </template>
            <template v-else>
              <div class="slot-empty-hint" v-if="canAdjust">
                + 空
              </div>
            </template>
          </div>
        </template>
      </div>

      <el-empty v-else-if="!loading" description="该周无课表实例数据" />
    </el-card>

    <!-- 变轨弹窗 -->
    <el-dialog
      v-model="adjustDialogVisible"
      title="教务变轨 — 调课/代课"
      width="480px"
      :close-on-click-modal="false"
    >
      <div v-if="adjustTarget" class="adjust-dialog-content">
        <el-descriptions :column="1" border size="small" class="adjust-info">
          <el-descriptions-item label="日期">{{ adjustTarget.date }}</el-descriptions-item>
          <el-descriptions-item label="节次">第{{ adjustTarget.period_index }}节</el-descriptions-item>
          <el-descriptions-item label="当前学科">
            {{ getSubjectName(adjustTarget.subject_id) }}
            <span class="dim-text">(ID: {{ adjustTarget.subject_id }})</span>
          </el-descriptions-item>
          <el-descriptions-item label="当前教师">
            {{ getTeacherName(adjustTarget.teacher_id) }}
            <span class="dim-text">(ID: {{ adjustTarget.teacher_id }})</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-form :model="adjustForm" label-width="90px" style="margin-top: 16px">
          <el-form-item label="新学科" required>
            <el-select
              v-model="adjustForm.subject_id"
              filterable
              placeholder="选择替换学科"
              style="width: 100%"
            >
              <el-option
                v-for="c in courseList"
                :key="c.id"
                :label="c.name"
                :value="c.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="新教师" required>
            <el-select
              v-model="adjustForm.teacher_id"
              filterable
              placeholder="选择代课教师"
              style="width: 100%"
            >
              <el-option
                v-for="t in teacherList"
                :key="t.id"
                :label="t.display_name"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="变轨原因">
            <el-input
              v-model="adjustForm.adjustment_reason"
              type="textarea"
              :rows="2"
              maxlength="255"
              show-word-limit
              placeholder="如: 教师请假/教研活动/临时调课..."
            />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="adjustDialogVisible = false">取消</el-button>
        <el-button
          type="warning"
          :loading="adjusting"
          @click="doAdjust"
        >
          执行变轨
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Refresh, User, WarningFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import {
  getTimetableInstances,
  adjustTimetableInstance,
  type TimetableInstance,
  type AdjustTimetablePayload,
} from '@/api/timetable'
import { listCourses, type Course } from '@/api/timetable'
import { listTeachers, type TeacherListItem } from '@/api/teachers'

// ── Props & External Data ──

const props = defineProps<{
  classList: any[]
}>()

const userStore = useUserStore()

// ── 响应式状态 ──

const loading = ref(false)
const adjusting = ref(false)
const selectedClassId = ref<number | null>(null)
const weekDate = ref<string>(getMondayOfThisWeek())
const showAdjustedOnly = ref(false)

const instances = ref<TimetableInstance[]>([])
const courseList = ref<Course[]>([])
const teacherList = ref<TeacherListItem[]>([])

// 变轨弹窗
const adjustDialogVisible = ref(false)
const adjustTarget = ref<TimetableInstance | null>(null)
const adjustForm = ref<AdjustTimetablePayload>({
  subject_id: 0,
  teacher_id: 0,
  adjustment_reason: '',
})

// ── 计算属性 ──

const canAdjust = computed(() => {
  const role = (userStore.userInfo?.role || '').toUpperCase()
  return role === 'MS_ADMIN' || role === 'GRADE_LEADER'
})

const courseMap = computed(() => {
  const m = new Map<number, Course>()
  courseList.value.forEach((c) => m.set(c.id, c))
  return m
})

const teacherMap = computed(() => {
  const m = new Map<number, TeacherListItem>()
  teacherList.value.forEach((t) => m.set(t.id, t))
  return m
})

const adjustedCount = computed(() => instances.value.filter((i) => i.is_adjusted).length)

// 7天日期数组
const weekDays = computed(() => {
  const monday = new Date(weekDate.value)
  const today = new Date()
  const todayStr = today.toISOString().slice(0, 10)
  const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const days = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    const dateStr = d.toISOString().slice(0, 10)
    days.push({
      dateStr,
      label: dayNames[i],
      dateLabel: `${d.getMonth() + 1}/${d.getDate()}`,
      isToday: dateStr === todayStr,
    })
  }
  return days
})

const currentWeekLabel = computed(() => {
  const days = weekDays.value
  if (days.length === 0) return ''
  return `${days[0].dateStr} ~ ${days[6].dateStr}`
})

// ── 常量 ──

// 梨江标准作息时间表 (8节正课)
const periodTimes = [
  '07:40-08:25',
  '08:35-09:20',
  '09:50-10:35',
  '10:45-11:30',
  '11:40-12:25',
  '14:00-14:45',
  '14:55-15:40',
  '15:50-16:35',
]

// 学科颜色映射
const subjectColors = [
  '#409EFF', '#67C23A', '#E6A23C', '#F56C6C',
  '#909399', '#9B59B6', '#1ABC9C', '#3498DB',
  '#E74C3C', '#2ECC71', '#F39C12', '#95A5A6',
]

// ── 工具函数 ──

function getMondayOfThisWeek(): string {
  const today = new Date()
  const dayOfWeek = today.getDay() || 7 // 周日=7
  const monday = new Date(today)
  monday.setDate(today.getDate() - dayOfWeek + 1)
  return monday.toISOString().slice(0, 10)
}

function getCell(period: number, dateStr: string): TimetableInstance | undefined {
  return instances.value.find(
    (i) => i.period_index === period && i.date === dateStr
  )
}

function getSubjectName(subjectId: number): string {
  return courseMap.value.get(subjectId)?.name || `学科#${subjectId}`
}

function getTeacherName(teacherId: number): string {
  return teacherMap.value.get(teacherId)?.display_name || `教师#${teacherId}`
}

function getSubjectColor(subjectId: number): string {
  const course = courseMap.value.get(subjectId)
  if (course?.color) return course.color
  return subjectColors[subjectId % subjectColors.length]
}

// ── 数据拉取 ──

async function fetchInstances() {
  if (!selectedClassId.value) return
  loading.value = true
  try {
    const startDate = weekDays.value[0].dateStr
    const endDate = weekDays.value[6].dateStr
    const res = await getTimetableInstances(selectedClassId.value, startDate, endDate)
    let data = res.instances || []
    if (showAdjustedOnly.value) {
      data = data.filter((i) => i.is_adjusted)
    }
    instances.value = data
  } catch (err: any) {
    ElMessage.error(`加载课表实例失败: ${err?.message || '未知错误'}`)
    instances.value = []
  } finally {
    loading.value = false
  }
}

async function fetchLookupData() {
  try {
    const [cRes, tRes] = await Promise.all([
      listCourses(),
      listTeachers({ page_size: 300 }),
    ])
    courseList.value = cRes
    teacherList.value = tRes.teachers
  } catch (err) {
    // 降级: 无lookup数据也能显示ID
  }
}

// ── 事件处理 ──

function onClassChange() {
  fetchInstances()
}

function onWeekChange() {
  fetchInstances()
}

function toggleAdjustedOnly() {
  showAdjustedOnly.value = !showAdjustedOnly.value
  fetchInstances()
}

function onCellDblClick(period: number, dateStr: string) {
  const cell = getCell(period, dateStr)
  if (!cell) {
    if (canAdjust.value) {
      ElMessage.info('该时段无课表实例, 无法变轨')
    }
    return
  }
  if (!canAdjust.value) {
    ElMessage.warning('您没有变轨权限 (需教务管理员或年级组长)')
    return
  }
  // 打开变轨弹窗
  adjustTarget.value = cell
  adjustForm.value = {
    subject_id: cell.subject_id,
    teacher_id: cell.teacher_id,
    adjustment_reason: '',
  }
  adjustDialogVisible.value = true
}

async function doAdjust() {
  if (!adjustTarget.value) return
  if (!adjustForm.value.subject_id || !adjustForm.value.teacher_id) {
    ElMessage.warning('请选择新学科和新教师')
    return
  }

  // 如果没有变化, 提示
  const target = adjustTarget.value
  if (
    adjustForm.value.subject_id === target.subject_id &&
    adjustForm.value.teacher_id === target.teacher_id
  ) {
    ElMessage.warning('学科和教师均未变化, 无需变轨')
    return
  }

  adjusting.value = true
  try {
    const res = await adjustTimetableInstance(target.id, adjustForm.value)
    if (res.status === 'success') {
      // 变轨成功 — 拉响通知
      const d = res.data
      const oldSubj = getSubjectName(d.old_subject_id)
      const newSubj = getSubjectName(d.new_subject_id)
      const oldTeach = getTeacherName(d.old_teacher_id)
      const newTeach = getTeacherName(d.new_teacher_id)

      ElNotification({
        title: '教务变轨成功',
        type: 'success',
        duration: 5000,
        message: `${d.date} 第${target.period_index}节: ${oldSubj}→${newSubj}, ${oldTeach}→${newTeach}`,
      })

      // 局部刷新: 更新对应实例的本地数据 (无需重新拉API)
      const idx = instances.value.findIndex((i) => i.id === target.id)
      if (idx >= 0) {
        instances.value[idx] = {
          ...instances.value[idx],
          subject_id: adjustForm.value.subject_id,
          teacher_id: adjustForm.value.teacher_id,
          is_adjusted: true,
        }
      }

      adjustDialogVisible.value = false
    } else {
      ElMessage.error(`变轨失败: ${res.msg || '未知错误'}`)
    }
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error(`变轨请求失败: ${detail}`)
  } finally {
    adjusting.value = false
  }
}

// ── 生命周期 ──

onMounted(async () => {
  await fetchLookupData()
  // 如果外部传入了班级列表, 默认选第一个
  if (props.classList.length > 0) {
    selectedClassId.value = props.classList[0].id
    fetchInstances()
  }
})

// 监听外部classList变化
watch(
  () => props.classList,
  (newList) => {
    if (newList.length > 0 && !selectedClassId.value) {
      selectedClassId.value = newList[0].id
      fetchInstances()
    }
  },
  { deep: true }
)
</script>

<style scoped>
.instance-grid-wrapper {
  padding: 0;
}

.control-bar {
  margin-bottom: 12px;
}
.control-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.control-left {
  flex: 1;
}
.control-right {
  flex-shrink: 0;
  margin-left: 12px;
}

.grid-card {
  overflow-x: auto;
}
.grid-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.grid-title {
  font-weight: 700;
  font-size: 15px;
}
.grid-hint {
  font-size: 12px;
  color: #909399;
}

/* ── 时空网格布局 ── */
.timetable-grid {
  display: grid;
  grid-template-columns: 90px repeat(7, minmax(120px, 1fr));
  gap: 4px;
  min-width: 950px;
}

.grid-cell {
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  min-height: 64px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

/* 角落 */
.grid-corner {
  background: #f5f7fa;
  font-weight: 700;
  text-align: center;
  align-items: center;
  color: #606266;
}

/* 日期表头 */
.grid-day-header {
  background: #ecf5ff;
  text-align: center;
  align-items: center;
  font-weight: 600;
  min-height: 48px;
}
.grid-day-header.is-today {
  background: #fef0f0;
  border: 2px solid #f56c6c;
}
.day-name {
  font-size: 14px;
  color: #303133;
}
.day-date {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

/* 节次标签 */
.grid-period-label {
  background: #f5f7fa;
  align-items: center;
  text-align: center;
}
.period-num {
  font-weight: 700;
  font-size: 13px;
  color: #303133;
}
.period-time {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

/* 课节格子 */
.grid-slot {
  background: #e8f4fd;
  border-left: 3px solid #409eff;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.grid-slot:hover {
  background: #d6ecff;
  transform: scale(1.02);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
  z-index: 1;
}
.grid-slot.is-today-col {
  background: #fdf6ec;
}

/* 空格子 */
.grid-slot.is-empty {
  background: #fafafa;
  border-left: 3px solid #ebeef5;
}
.grid-slot.is-empty:hover {
  background: #f5f7fa;
}

/* 已变轨格子弹窗 */
.grid-slot.is-adjusted {
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border: 2px solid #e6a23c;
  border-left-width: 4px;
  animation: pulse-adjusted 2s ease-in-out infinite;
}
@keyframes pulse-adjusted {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(230, 162, 60, 0); }
}

/* 课节内容 */
.slot-subject {
  font-weight: 700;
  font-size: 14px;
  color: #303133;
  border-left: 3px solid #409eff;
  padding-left: 4px;
  margin-bottom: 2px;
}
.slot-teacher {
  font-size: 11px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 2px;
}
.slot-adjusted-badge {
  position: absolute;
  top: 2px;
  right: 4px;
  font-size: 10px;
  color: #e6a23c;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 2px;
}
.slot-empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  text-align: center;
  align-self: center;
}

/* ── 变轨弹窗 ── */
.adjust-dialog-content {
  /* 保持紧凑 */
}
.adjust-info {
  margin-bottom: 8px;
}
.dim-text {
  color: #c0c4cc;
  font-size: 11px;
  margin-left: 4px;
}

/* ── 响应式 ── */
@media (max-width: 1200px) {
  .timetable-grid {
    min-width: 950px;
  }
  .grid-card {
    overflow-x: scroll;
  }
}
</style>
