<template>
  <div class="teacher-workload">
    <el-page-header @back="$router.back()" title="返回">
      <template #content>
        <span>工作量统计 — {{ stats?.display_name || '' }}</span>
      </template>
    </el-page-header>

    <el-card class="info-card" v-loading="loading">
      <template #header><h4>统计汇总</h4></template>
      <el-row :gutter="16" v-if="stats">
        <el-col :span="6">
          <el-statistic title="累计学期" :value="stats.total_semesters" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="平均周课时" :value="stats.avg_weekly_periods" :precision="1" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="平均带班数" :value="stats.avg_class_count" :precision="1" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="累计任教科目" :value="stats.total_subjects" />
        </el-col>
      </el-row>
    </el-card>

    <el-card class="info-card">
      <template #header>
        <div class="card-header">
          <h4>工作量明细</h4>
          <el-button type="primary" size="small" @click="showAddDialog = true">新增记录</el-button>
        </div>
      </template>
      <el-table :data="stats?.workloads || []" stripe>
        <el-table-column prop="semester" label="学期" width="140" />
        <el-table-column prop="weekly_periods" label="周课时" width="80" />
        <el-table-column prop="class_count" label="任教班级数" width="100" />
        <el-table-column prop="subject_count" label="科目数" width="80" />
        <el-table-column label="班主任" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_head_teacher" type="warning" size="small">是</el-tag>
            <span v-else>否</span>
          </template>
        </el-table-column>
        <el-table-column label="兼任" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="d in row.extra_duties || []" :key="d" size="small" style="margin-right:4px">{{ d }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="综合评分" width="100">
          <template #default="{ row }">
            <span v-if="row.total_workload_score != null">{{ row.total_workload_score.toFixed(1) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增工作量弹窗 -->
    <el-dialog v-model="showAddDialog" title="新增工作量记录" width="450px">
      <el-form :model="wlForm" label-width="100px">
        <el-form-item label="学期" required>
          <el-input v-model="wlForm.semester" placeholder="2025-2026-1" />
        </el-form-item>
        <el-form-item label="周课时量" required>
          <el-input-number v-model="wlForm.weekly_periods" :min="0" :max="40" />
        </el-form-item>
        <el-form-item label="任教班级数">
          <el-input-number v-model="wlForm.class_count" :min="0" :max="30" />
        </el-form-item>
        <el-form-item label="科目数">
          <el-input-number v-model="wlForm.subject_count" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="兼任职务">
          <el-checkbox-group v-model="wlForm.extra_duties">
            <el-checkbox label="年级组长" /><el-checkbox label="教研组长" />
            <el-checkbox label="备课组长" /><el-checkbox label="社团指导教师" />
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveWorkload" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getWorkloadStats, addWorkload, type WorkloadStats } from '@/api/teachers'

const route = useRoute()
const userId = Number(route.params.id)
const loading = ref(false)
const saving = ref(false)
const stats = ref<WorkloadStats | null>(null)
const showAddDialog = ref(false)
const wlForm = ref({ semester: '', weekly_periods: 0, class_count: 0, subject_count: 1, extra_duties: [] as string[] })

async function fetchStats() {
  loading.value = true
  try {
    const res = await getWorkloadStats(userId)
    stats.value = res
  } finally {
    loading.value = false
  }
}

async function saveWorkload() {
  saving.value = true
  try {
    await addWorkload(userId, wlForm.value)
    showAddDialog.value = false
    wlForm.value = { semester: '', weekly_periods: 0, class_count: 0, subject_count: 1, extra_duties: [] }
    await fetchStats()
  } finally {
    saving.value = false
  }
}

onMounted(fetchStats)
</script>

<style scoped>
.teacher-workload { padding: 0; }
.info-card { margin-top: 12px; }
.card-header { display:flex; justify-content:space-between; align-items:center; }
.card-header h4 { margin:0; }
</style>
