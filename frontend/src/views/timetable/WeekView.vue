<template>
  <div class="week-view">
    <el-page-header @back="$router.back()" title="返回">
      <template #content>
        <span>周课表 — {{ schedule?.class_name || '' }} ({{ schedule?.grade_name || '' }})</span>
      </template>
    </el-page-header>

    <el-card class="info-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <h4>{{ schedule?.semester || '' }} 学期课表</h4>
          <el-tag>班级课表</el-tag>
        </div>
      </template>

      <div v-if="schedule" class="schedule-grid">
        <div class="day-header" v-for="d in DAYS" :key="d.day">{{ d.label }}</div>
        <div v-for="d in DAYS" :key="'col-'+d.day" class="day-column">
          <div
            v-for="slot in (schedule.schedule[String(d.day)] || [])"
            :key="slot.id"
            class="slot-card"
          >
            <div class="slot-course">{{ slot.course_name }}</div>
            <div class="slot-meta">
              <span>{{ slot.teacher_name }}</span>
              <span v-if="slot.classroom_name">@{{ slot.classroom_name }}</span>
            </div>
            <div class="slot-period">
              第{{ slot.period_start }}{{ slot.period_end > slot.period_start ? '-' + slot.period_end : '' }}节
              <el-tag v-if="slot.week_pattern !== 'every'" size="small" type="warning" style="margin-left:4px">
                {{ slot.week_pattern === 'odd' ? '单周' : '双周' }}
              </el-tag>
            </div>
          </div>
          <el-empty v-if="!schedule.schedule[String(d.day)]?.length" description="无课" :image-size="40" />
        </div>
      </div>
      <el-empty v-else description="未选择学期" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getClassWeeklySchedule, type WeeklySchedule } from '@/api/timetable'

const DAYS = [
  { day: 1, label: '周一' }, { day: 2, label: '周二' }, { day: 3, label: '周三' },
  { day: 4, label: '周四' }, { day: 5, label: '周五' }, { day: 6, label: '周六' }, { day: 7, label: '周日' },
]

const route = useRoute()
const classId = Number(route.params.classId)
const semester = (route.query.semester as string) || '2025-2026-2'
const loading = ref(false)
const schedule = ref<WeeklySchedule | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    const res = await getClassWeeklySchedule(classId, semester)
    schedule.value = res.data
  } finally { loading.value = false }
})
</script>

<style scoped>
.week-view { padding: 0; }
.info-card { margin-top: 12px; }
.card-header { display:flex; justify-content:space-between; align-items:center; }
.card-header h4 { margin:0; }

.schedule-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
}
.day-header {
  text-align: center;
  font-weight: 700;
  font-size: 15px;
  padding: 8px;
  background: #f0f2f5;
  border-radius: 6px;
}
.day-column {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.slot-card {
  background: #e8f4fd;
  border-left: 4px solid #409eff;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
}
.slot-course { font-weight: 700; font-size: 14px; color: #303133; }
.slot-meta { color: #606266; margin-top: 2px; display: flex; gap: 8px; }
.slot-period { color: #909399; font-size: 12px; margin-top: 2px; }
</style>
