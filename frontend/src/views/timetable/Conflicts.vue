<template>
  <div class="conflicts-panel">
    <el-card class="header-card">
      <div class="header">
        <h3>排课冲突告警</h3>
        <div>
          <el-select v-model="filterResolution" clearable placeholder="全部状态" @change="fetchConflicts" style="width:140px;margin-right:8px">
            <el-option label="未解决" value="unresolved" />
            <el-option label="已解决" value="resolved_by_move" />
            <el-option label="已取消" value="resolved_by_cancel" />
            <el-option label="已忽略" value="ignored" />
          </el-select>
          <el-button type="primary" @click="fetchConflicts">刷新</el-button>
        </div>
      </div>
    </el-card>

    <el-card>
      <el-table :data="conflicts" stripe v-loading="loading">
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.conflict_type === 'teacher' ? 'danger' : 'warning'" size="small">
              {{ conflictTypeLabel(row.conflict_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="严重程度" width="90">
          <template #default="{ row }">
            <el-tag :type="row.severity === 'error' ? 'danger' : 'warning'" size="small">
              {{ row.severity === 'error' ? '硬冲突' : '软冲突' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conflict_detail" label="冲突详情" min-width="280" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.resolution === 'unresolved' ? 'danger' : 'success'" size="small">
              {{ resolutionLabel(row.resolution) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <template v-if="row.resolution === 'unresolved'">
              <el-button type="primary" size="small" @click="doResolve(row.id, 'resolved_by_move')">调整解决</el-button>
              <el-button type="warning" size="small" @click="doResolve(row.id, 'ignored')">忽略</el-button>
            </template>
            <span v-else style="color:#909399">已处理</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listConflicts, resolveConflict } from '@/api/timetable'

const loading = ref(false)
const conflicts = ref<any[]>([])
const filterResolution = ref<string | null>(null)

function conflictTypeLabel(t: string) {
  const m: Record<string, string> = { teacher: '教师冲突', classroom: '教室冲突', class: '班级冲突', capacity: '容量超限' }
  return m[t] || t
}
function resolutionLabel(r: string) {
  const m: Record<string, string> = { unresolved: '未解决', resolved_by_move: '已调整', resolved_by_cancel: '已取消', ignored: '已忽略' }
  return m[r] || r
}

async function fetchConflicts() {
  loading.value = true
  try {
    const res = await listConflicts({ resolution: filterResolution.value || undefined })
    conflicts.value = res.data.items || res.data
  } finally { loading.value = false }
}

async function doResolve(id: number, resolution: string) {
  await resolveConflict(id, resolution)
  fetchConflicts()
}

onMounted(fetchConflicts)
</script>

<style scoped>
.conflicts-panel { padding: 0; }
.header-card { margin-bottom: 12px; }
.header { display:flex; justify-content:space-between; align-items:center; }
.header h3 { margin:0; }
</style>
