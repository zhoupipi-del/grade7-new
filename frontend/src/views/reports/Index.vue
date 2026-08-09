<template>
  <div class="reports-console">
    <!-- ═══════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ═══════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Files /></el-icon>
          报告工作台
        </h2>
        <span class="page-subtitle">期末白皮书 · RDI 风险态势 · PDF 异步导出引擎</span>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="small">
          学期: {{ semester }} · 活跃任务: {{ activeTaskCount }}
        </el-tag>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ -->
    <!-- Tabs: 期末白皮书 | PDF导出               -->
    <!-- ═══════════════════════════════════════ -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange" class="reports-tabs">

      <!-- ── Tab 1: 期末白皮书 ────────────────── -->
      <el-tab-pane name="whitepaper">
        <template #label>
          <span class="tab-label">
            <el-icon><DataAnalysis /></el-icon> 期末白皮书
          </span>
        </template>

        <!-- ═══ Admin / GradeLeader: 全校 RDI 态势 ═══ -->
        <div v-if="isBatchRole" v-loading="rdiLoading" class="rdi-section">
          <!-- 统计卡片行 -->
          <el-row v-if="rdiSummary" :gutter="12" class="stat-row">
            <el-col :span="6">
              <div class="stat-card stat-total">
                <div class="stat-label">总扫描人数</div>
                <div class="stat-value">{{ rdiSummary.total_students_scanned }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card stat-red">
                <div class="stat-label">红灯干预</div>
                <div class="stat-value">{{ rdiSummary.risk_distribution.red_intervention }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card stat-yellow">
                <div class="stat-label">黄灯关注</div>
                <div class="stat-value">{{ rdiSummary.risk_distribution.yellow_attention }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card stat-green">
                <div class="stat-label">绿灯正常</div>
                <div class="stat-value">{{ rdiSummary.risk_distribution.green_normal }}</div>
              </div>
            </el-col>
          </el-row>

          <!-- 饼图 + 热力排行 -->
          <el-row v-if="rdiSummary" :gutter="12" class="chart-row">
            <el-col :span="10">
              <div class="panel-card">
                <div class="panel-title">风险分布</div>
                <div ref="riskChartRef" class="chart-container"></div>
              </div>
            </el-col>
            <el-col :span="14">
              <div class="panel-card">
                <div class="panel-title">班级热力排行 TOP 5</div>
                <el-table
                  :data="rdiSummary.department_heat_ranking"
                  size="small"
                  class="dark-table"
                >
                  <el-table-column label="班级" prop="class_name" min-width="100" />
                  <el-table-column label="红灯" width="80" align="center">
                    <template #default="{ row }: any">
                      <span :class="{ 'num-red': row.red_count > 0 }">{{ row.red_count }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="黄灯" width="80" align="center">
                    <template #default="{ row }: any">
                      <span :class="{ 'num-yellow': row.yellow_count > 0 }">{{ row.yellow_count }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="总 RDI" width="100" align="center">
                    <template #default="{ row }: any">
                      {{ formatRdiScore(row.total_rdi) }}
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </el-col>
          </el-row>

          <!-- 高危花名册 -->
          <div
            v-if="rdiSummary && rdiSummary.top_critical_list.length > 0"
            class="panel-card"
          >
            <div class="panel-header">
              <div class="panel-title">高危学生花名册</div>
              <el-button
                type="danger"
                :icon="Download"
                :loading="exportingHighRisk"
                size="small"
                @click="handleExportHighRisk"
              >
                导出花名册
              </el-button>
            </div>
            <el-table
              :data="rdiSummary.top_critical_list"
              size="small"
              class="dark-table"
              stripe
            >
              <el-table-column label="姓名" prop="student_name" width="80" />
              <el-table-column label="班级" prop="class_name" width="80" />
              <el-table-column label="RDI" width="70" align="center">
                <template #default="{ row }: any">
                  <span class="rdi-score">{{ formatRdiScore(row.current_rdi) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="等级" width="90" align="center">
                <template #default="{ row }: any">
                  <el-tag :type="riskLevelTag(row.risk_level)" size="small" effect="dark">
                    {{ riskLevelLabel(row.risk_level) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="行为" width="70" align="center">
                <template #default="{ row }: any">{{ formatSigma(row.breakdown?.behavior) }}</template>
              </el-table-column>
              <el-table-column label="考勤" width="70" align="center">
                <template #default="{ row }: any">{{ formatSigma(row.breakdown?.attendance) }}</template>
              </el-table-column>
              <el-table-column label="学业" width="70" align="center">
                <template #default="{ row }: any">{{ formatSigma(row.breakdown?.score) }}</template>
              </el-table-column>
              <el-table-column label="心理" width="70" align="center">
                <template #default="{ row }: any">{{ formatSigma(row.breakdown?.psych) }}</template>
              </el-table-column>
              <el-table-column label="最近预警" min-width="180" show-overflow-tooltip>
                <template #default="{ row }: any">{{ row.latest_warning_reason || '—' }}</template>
              </el-table-column>
              <el-table-column label="AI 处方" min-width="200" show-overflow-tooltip>
                <template #default="{ row }: any">{{ row.ai_prescription_snippet || '—' }}</template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 空状态 -->
          <el-empty
            v-if="!rdiLoading && !rdiSummary"
            description="暂无 RDI 态势数据，请稍后重试"
            :image-size="80"
          />
        </div>

        <!-- ═══ ClassTeacher: 本班期末德育大盘 ═══ -->
        <div v-else v-loading="classReportLoading" class="class-section">
          <template v-if="classReport">
            <!-- 班级概览 -->
            <el-row :gutter="12" class="stat-row">
              <el-col :span="8">
                <div class="stat-card stat-blue">
                  <div class="stat-label">班级</div>
                  <div class="stat-value text-md">{{ classReport.class_name }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="stat-card stat-total">
                  <div class="stat-label">学生人数</div>
                  <div class="stat-value">{{ classReport.student_count }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="stat-card stat-green">
                  <div class="stat-label">生成时间</div>
                  <div class="stat-value text-md">{{ formatDateTime(classReport.generated_at) }}</div>
                </div>
              </el-col>
            </el-row>

            <!-- 风险分布 -->
            <el-row :gutter="12" class="stat-row">
              <el-col :span="8">
                <div class="stat-card stat-red">
                  <div class="stat-label">红灯干预</div>
                  <div class="stat-value">{{ classReport.risk_distribution.red_intervention }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="stat-card stat-yellow">
                  <div class="stat-label">黄灯关注</div>
                  <div class="stat-value">{{ classReport.risk_distribution.yellow_attention }}</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="stat-card stat-green">
                  <div class="stat-label">绿灯正常</div>
                  <div class="stat-value">{{ classReport.risk_distribution.green_normal }}</div>
                </div>
              </el-col>
            </el-row>

            <!-- 高危学生列表 -->
            <div
              v-if="classReport.high_risk_students.length > 0"
              class="panel-card"
            >
              <div class="panel-title">高危学生</div>
              <el-table
                :data="classReport.high_risk_students"
                size="small"
                class="dark-table"
                stripe
              >
                <el-table-column label="姓名" prop="student_name" width="100" />
                <el-table-column label="RDI" width="80" align="center">
                  <template #default="{ row }: any">
                    <span class="rdi-score">{{ formatRdiScore(row.current_rdi) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="等级" width="100" align="center">
                  <template #default="{ row }: any">
                    <el-tag :type="riskLevelTag(row.risk_level)" size="small" effect="dark">
                      {{ riskLevelLabel(row.risk_level) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="行为" width="80" align="center">
                  <template #default="{ row }: any">{{ formatSigma(row.breakdown?.behavior) }}</template>
                </el-table-column>
                <el-table-column label="考勤" width="80" align="center">
                  <template #default="{ row }: any">{{ formatSigma(row.breakdown?.attendance) }}</template>
                </el-table-column>
                <el-table-column label="学业" width="80" align="center">
                  <template #default="{ row }: any">{{ formatSigma(row.breakdown?.score) }}</template>
                </el-table-column>
                <el-table-column label="心理" width="80" align="center">
                  <template #default="{ row }: any">{{ formatSigma(row.breakdown?.psych) }}</template>
                </el-table-column>
                <el-table-column label="最近预警" min-width="200" show-overflow-tooltip>
                  <template #default="{ row }: any">{{ row.latest_warning_reason || '—' }}</template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 三大摘要 -->
            <el-row :gutter="12" class="summary-row">
              <!-- 考勤摘要 -->
              <el-col :span="8">
                <div class="panel-card summary-card">
                  <div class="panel-title">考勤摘要</div>
                  <div class="summary-list">
                    <div class="summary-item">
                      <span class="summary-label">应到天数</span>
                      <span class="summary-value">{{ classReport.attendance_summary.total_days }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">缺勤天数</span>
                      <span
                        class="summary-value"
                        :class="{ 'num-red': classReport.attendance_summary.absent_days > 0 }"
                      >{{ classReport.attendance_summary.absent_days }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">迟到天数</span>
                      <span
                        class="summary-value"
                        :class="{ 'num-yellow': classReport.attendance_summary.late_days > 0 }"
                      >{{ classReport.attendance_summary.late_days }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">早退天数</span>
                      <span class="summary-value">{{ classReport.attendance_summary.early_leave_days }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">出勤率</span>
                      <span class="summary-value">{{ formatPercent(classReport.attendance_summary.attendance_rate) }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">连续缺勤</span>
                      <span
                        class="summary-value"
                        :class="{ 'num-red': classReport.attendance_summary.consecutive_absence >= 3 }"
                      >{{ classReport.attendance_summary.consecutive_absence }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">最近缺勤</span>
                      <span class="summary-value">{{ formatDateTime(classReport.attendance_summary.last_absence_date) }}</span>
                    </div>
                  </div>
                </div>
              </el-col>

              <!-- 纪律摘要 -->
              <el-col :span="8">
                <div class="panel-card summary-card">
                  <div class="panel-title">纪律摘要</div>
                  <div class="summary-list">
                    <div class="summary-item">
                      <span class="summary-label">事件总数</span>
                      <span class="summary-value">{{ classReport.discipline_summary.total_incidents }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">待处理</span>
                      <span
                        class="summary-value"
                        :class="{ 'num-yellow': classReport.discipline_summary.pending_count > 0 }"
                      >{{ classReport.discipline_summary.pending_count }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">已处理</span>
                      <span class="summary-value">{{ classReport.discipline_summary.resolved_count }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">最高严重等级</span>
                      <span class="summary-value">{{ classReport.discipline_summary.max_severity || '—' }}</span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">最近事件</span>
                      <span class="summary-value">{{ formatDateTime(classReport.discipline_summary.latest_incident_date) }}</span>
                    </div>
                  </div>
                </div>
              </el-col>

              <!-- 学业摘要 -->
              <el-col :span="8">
                <div class="panel-card summary-card">
                  <div class="panel-title">学业摘要</div>
                  <div class="summary-list">
                    <div class="summary-item">
                      <span class="summary-label">平均分</span>
                      <span class="summary-value">
                        {{ classReport.academic_summary.average_score !== null ? classReport.academic_summary.average_score.toFixed(1) : '—' }}
                      </span>
                    </div>
                    <div class="summary-item">
                      <span class="summary-label">年级排名</span>
                      <span class="summary-value">
                        {{ classReport.academic_summary.rank_in_grade !== null ? `第${classReport.academic_summary.rank_in_grade}名` : '—' }}
                      </span>
                    </div>
                    <div
                      v-if="classReport.academic_summary.subject_warnings.length > 0"
                      class="summary-item"
                    >
                      <span class="summary-label">学科预警</span>
                      <div class="warning-tags">
                        <el-tag
                          v-for="w in classReport.academic_summary.subject_warnings"
                          :key="w"
                          type="warning"
                          size="small"
                          effect="dark"
                        >{{ w }}</el-tag>
                      </div>
                    </div>
                  </div>
                </div>
              </el-col>
            </el-row>
          </template>

          <!-- 空状态 -->
          <el-empty
            v-if="!classReportLoading && !classReport"
            description="暂无班级报告数据"
            :image-size="80"
          />
        </div>
      </el-tab-pane>

      <!-- ── Tab 2: PDF 导出工作台 ─────────────── -->
      <el-tab-pane name="pdf">
        <template #label>
          <span class="tab-label">
            <el-icon><Files /></el-icon> PDF 导出
          </span>
        </template>

        <el-row :gutter="16" class="workbench-body">
          <!-- Left: Export Form -->
          <el-col :span="8">
            <div class="export-panel">
              <!-- 单班导出 -->
              <div class="panel-card export-card">
                <div class="panel-title">
                  <el-icon><Document /></el-icon> 班级德育报告
                </div>
                <el-form label-width="80px" size="default" class="export-form">
                  <el-form-item label="报告类型">
                    <el-radio-group v-model="singleForm.report_type">
                      <el-radio-button
                        v-for="rt in REPORT_TYPES"
                        :key="rt.value"
                        :value="rt.value"
                      >{{ rt.label }}</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="目标班级">
                    <el-select
                      v-model="singleForm.class_id"
                      placeholder="选择班级"
                      filterable
                      style="width: 100%"
                    >
                      <el-option
                        v-for="c in classOptions"
                        :key="c.id"
                        :label="c.name"
                        :value="c.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item
                    v-if="singleForm.report_type === 'student_individual'"
                    label="目标学生"
                  >
                    <el-select
                      v-model="singleForm.student_id"
                      placeholder="(可选) 选择学生，留空生成全班"
                      filterable
                      clearable
                      style="width: 100%"
                    >
                      <el-option
                        v-for="s in studentOptions"
                        :key="s.id"
                        :label="`${s.name} (${s.student_no})`"
                        :value="s.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button
                      type="primary"
                      :icon="VideoPlay"
                      :loading="singleExporting"
                      :disabled="!singleForm.class_id"
                      @click="triggerSingleExport"
                      style="width: 100%"
                    >开始生成报告</el-button>
                  </el-form-item>
                </el-form>
                <div class="export-info">
                  <el-icon><Clock /></el-icon>
                  <span>报告通过 Celery 异步生成，预计耗时 5-15 秒，完成后可下载 PDF</span>
                </div>
              </div>

              <!-- 年级批量导出 -->
              <div v-if="isBatchRole" class="panel-card export-card">
                <div class="panel-title">
                  <el-icon><Collection /></el-icon> 年级批量导出
                </div>
                <el-form label-width="80px" size="default" class="export-form">
                  <el-form-item label="目标年级">
                    <el-select
                      v-model="batchForm.grade_id"
                      placeholder="选择年级"
                      filterable
                      style="width: 100%"
                    >
                      <el-option
                        v-for="g in gradeOptions"
                        :key="g.id"
                        :label="g.name"
                        :value="g.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button
                      type="success"
                      :icon="VideoPlay"
                      :loading="batchExporting"
                      :disabled="!batchForm.grade_id"
                      @click="triggerBatchExport"
                      style="width: 100%"
                    >批量生成全年级报告</el-button>
                  </el-form-item>
                </el-form>
              </div>
            </div>
          </el-col>

          <!-- Right: Task List -->
          <el-col :span="16">
            <div class="panel-card task-list-card">
              <div class="panel-header">
                <div class="panel-title">
                  <el-icon><List /></el-icon> 导出任务列表
                </div>
                <div class="header-actions">
                  <el-button
                    size="small"
                    :icon="Refresh"
                    :loading="pollingActive"
                    @click="refreshAllTasks"
                  >刷新状态</el-button>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :disabled="completedTasks.length === 0"
                    @click="clearCompleted"
                  >清除已完成</el-button>
                </div>
              </div>

              <!-- 活跃任务进度卡片 -->
              <div v-if="activeTasks.length > 0" class="progress-section">
                <div
                  v-for="task in activeTasks"
                  :key="task.id"
                  class="progress-card"
                >
                  <div class="progress-header">
                    <span class="progress-title">
                      <el-tag :type="taskStateTagType(task.state)" size="small" effect="dark">
                        {{ taskStateLabel(task.state) }}
                      </el-tag>
                      <span class="progress-class">{{ task.className }}</span>
                      <span class="progress-type">{{ task.reportType === 'class_moral' ? '班级报告' : '学生报告' }}</span>
                    </span>
                    <span class="progress-pct">{{ task.progress }}%</span>
                  </div>
                  <el-progress
                    :percentage="task.progress"
                    :status="task.state === 'SUCCESS' ? 'success' : task.state === 'FAILURE' ? 'exception' : undefined"
                    :stroke-width="8"
                    :text-inside="false"
                  />
                  <div class="progress-footer">
                    <span class="progress-text">{{ task.statusText }}</span>
                    <span class="progress-time">{{ formatElapsed(task.createdAt) }}</span>
                  </div>
                </div>
              </div>

              <!-- 已完成任务列表 -->
              <div v-if="completedTasks.length > 0" class="completed-section">
                <div class="section-label">已完成报告</div>
                <el-table :data="completedTasks" size="small" stripe class="dark-table">
                  <el-table-column label="状态" width="80" align="center">
                    <template #default="{ row }: any">
                      <el-tag :type="row.state === 'SUCCESS' ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.state === 'SUCCESS' ? '完成' : '失败' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="班级" width="110">
                    <template #default="{ row }: any">{{ row.className }}</template>
                  </el-table-column>
                  <el-table-column label="类型" width="90">
                    <template #default="{ row }: any">
                      {{ row.reportType === 'class_moral' ? '班级报告' : '学生报告' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="文件名" min-width="200" show-overflow-tooltip>
                    <template #default="{ row }: any">
                      <span v-if="row.result?.filename" class="filename-text">{{ row.result.filename }}</span>
                      <span v-else class="error-text">{{ row.error || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="大小" width="80" align="center">
                    <template #default="{ row }: any">{{ formatFileSize(row.result?.file_size_kb) }}</template>
                  </el-table-column>
                  <el-table-column label="生成时间" width="110">
                    <template #default="{ row }: any">
                      {{ row.result?.generated_at ? formatTime(row.result.generated_at) : '—' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="120" align="center" fixed="right">
                    <template #default="{ row }: any">
                      <el-button
                        v-if="row.state === 'SUCCESS' && row.result?.download_url"
                        type="primary"
                        size="small"
                        link
                        :icon="Download"
                        @click="downloadReport(row)"
                      >下载</el-button>
                      <el-button
                        v-else
                        size="small"
                        type="danger"
                        link
                        :icon="Delete"
                        @click="removeTask(row.id)"
                      >删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>

              <!-- 空状态 -->
              <el-empty
                v-if="allTasks.length === 0"
                description="暂无导出任务，请在左侧选择班级并点击「开始生成报告」"
                :image-size="80"
              >
                <el-button type="primary" @click="demoTask">演示模式 (离线 Demo)</el-button>
              </el-empty>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  VideoPlay,
  Clock,
  Files,
  Collection,
  List,
  Refresh,
  Download,
  Delete,
  DataAnalysis,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import '@/utils/echarts'
import { useUserStore } from '@/store/user'
import { getClasses, getGrades, getStudents } from '@/api/classes'
import {
  exportMoralReport,
  exportGradeReport,
  getTaskStatus,
  taskStateTagType,
  taskStateLabel,
  formatFileSize,
  REPORT_TYPES,
  POLL_INTERVAL,
  MAX_POLL_COUNT,
  getDemoClasses,
  getDemoGrades,
  simulateTaskProgress,
  type TaskTracker,
  type ClassOption,
  type GradeOption,
  // RDI Whitepaper
  getRdiSummary,
  exportHighRiskStudents,
  getClassReport,
  riskLevelLabel,
  riskLevelTag,
  formatRdiScore,
  formatSigma,
  formatPercent,
  formatDateTime,
  type SchoolWideReportResponse,
  type ClassTeacherReportResponse,
  type RiskLevel,
} from '@/api/reports'

// ═══════════════════════════════════════════════════
// Store & Role
// ═══════════════════════════════════════════════════

const userStore = useUserStore()
const isBatchRole = computed(() =>
  ['MS_ADMIN', 'GRADE_LEADER'].includes(userStore.currentRole || ''),
)
const userClassId = computed(() => userStore.userInfo?.class_id || null)
const semester = '2025-2026-2'

// ═══════════════════════════════════════════════════
// Tab State
// ═══════════════════════════════════════════════════

const activeTab = ref('whitepaper')

// ═══════════════════════════════════════════════════
// RDI Whitepaper State (Tab 1)
// ═══════════════════════════════════════════════════

const rdiLoading = ref(false)
const rdiSummary = ref<SchoolWideReportResponse | null>(null)
const exportingHighRisk = ref(false)

const classReportLoading = ref(false)
const classReport = ref<ClassTeacherReportResponse | null>(null)

// ECharts
const riskChartRef = ref<HTMLElement | null>(null)
let riskChart: echarts.ECharts | null = null

// ═══════════════════════════════════════════════════
// PDF Export State (Tab 2)
// ═══════════════════════════════════════════════════

const singleForm = ref({
  report_type: 'class_moral',
  class_id: null as number | null,
  student_id: null as number | null,
})
const singleExporting = ref(false)

const batchForm = ref({
  grade_id: null as number | null,
})
const batchExporting = ref(false)

const classOptions = ref<ClassOption[]>([])
const gradeOptions = ref<GradeOption[]>([])
const studentOptions = ref<{ id: number; name: string; student_no: string }[]>([])

const tasks = ref<TaskTracker[]>([])
const pollingActive = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
const pollCount = ref(0)

// ═══════════════════════════════════════════════════
// Computed (PDF Export)
// ═══════════════════════════════════════════════════

const activeTasks = computed(() =>
  tasks.value.filter((t) => t.state === 'PENDING' || t.state === 'PROGRESS'),
)
const completedTasks = computed(() =>
  tasks.value.filter((t) => t.state === 'SUCCESS' || t.state === 'FAILURE'),
)
const allTasks = computed(() => [...activeTasks.value, ...completedTasks.value])
const activeTaskCount = computed(() => activeTasks.value.length)

// ═══════════════════════════════════════════════════
// RDI Whitepaper Functions
// ═══════════════════════════════════════════════════

async function loadRdiSummary() {
  rdiLoading.value = true
  try {
    const data = await getRdiSummary()
    rdiSummary.value = data
    nextTick(() => initRiskChart())
  } catch {
    ElMessage.error('加载 RDI 态势数据失败')
  } finally {
    rdiLoading.value = false
  }
}

async function loadClassReport() {
  if (!userClassId.value) {
    ElMessage.warning('未绑定班级，无法查看报告')
    return
  }
  classReportLoading.value = true
  try {
    const data = await getClassReport(userClassId.value)
    classReport.value = data
  } catch {
    ElMessage.error('加载班级报告失败')
  } finally {
    classReportLoading.value = false
  }
}

async function handleExportHighRisk() {
  exportingHighRisk.value = true
  try {
    const data = await exportHighRiskStudents()
    ElMessage.success(`已导出 ${data.total_exported} 名高危学生花名册`)
    // 更新花名册数据
    if (rdiSummary.value) {
      rdiSummary.value.top_critical_list = data.students
    }
  } catch {
    ElMessage.error('导出花名册失败')
  } finally {
    exportingHighRisk.value = false
  }
}

function initRiskChart() {
  if (!riskChartRef.value || !rdiSummary.value) return

  if (riskChart) {
    riskChart.dispose()
  }
  riskChart = echarts.init(riskChartRef.value)

  const dist = rdiSummary.value.risk_distribution
  riskChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      bottom: 0,
      textStyle: { color: '#8b949e', fontSize: 12 },
      itemWidth: 10,
      itemHeight: 10,
    },
    series: [
      {
        type: 'pie',
        radius: ['55%', '78%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 4,
          borderColor: '#0d1117',
          borderWidth: 2,
        },
        label: {
          show: true,
          color: '#c9d1d9',
          fontSize: 13,
          formatter: '{b}\n{c}',
        },
        labelLine: {
          lineStyle: { color: '#30363d' },
        },
        data: [
          { value: dist.red_intervention, name: '红灯干预', itemStyle: { color: '#f85149' } },
          { value: dist.yellow_attention, name: '黄灯关注', itemStyle: { color: '#d29922' } },
          { value: dist.green_normal, name: '绿灯正常', itemStyle: { color: '#3fb950' } },
        ],
      },
    ],
  })
}

function onTabChange(tabName: string | number) {
  if (tabName === 'whitepaper') {
    nextTick(() => {
      if (isBatchRole.value && rdiSummary.value) {
        initRiskChart()
      }
    })
  }
}

// ═══════════════════════════════════════════════════
// PDF Export Triggers
// ═══════════════════════════════════════════════════

async function triggerSingleExport() {
  if (!singleForm.value.class_id) {
    ElMessage.warning('请选择目标班级')
    return
  }
  singleExporting.value = true
  try {
    const res = await exportMoralReport({
      class_id: singleForm.value.class_id,
      semester,
      report_type: singleForm.value.report_type,
      student_id: singleForm.value.student_id || undefined,
    })
    const className =
      classOptions.value.find((c) => c.id === singleForm.value.class_id)?.name ||
      `班级#${singleForm.value.class_id}`
    tasks.value.unshift({
      id: res.task_id,
      classId: singleForm.value.class_id,
      className,
      reportType: singleForm.value.report_type,
      state: 'PENDING',
      progress: 0,
      statusText: '任务已提交，排队中...',
      createdAt: new Date(),
    })
    ElMessage.success(`任务已提交 (${res.task_id.slice(0, 8)}...)`)
    startPolling()
  } catch {
    ElMessage.error('提交任务失败，请重试')
  } finally {
    singleExporting.value = false
  }
}

async function triggerBatchExport() {
  if (!batchForm.value.grade_id) {
    ElMessage.warning('请选择目标年级')
    return
  }
  batchExporting.value = true
  try {
    const res = await exportGradeReport({
      grade_id: batchForm.value.grade_id,
      semester,
    })
    for (let i = 0; i < res.task_ids.length; i++) {
      const taskClassId = batchForm.value.grade_id
        ? (classOptions.value.filter((c: any) => c.grade_id === batchForm.value.grade_id)[i]?.id || (i + 1))
        : (i + 1)
      const taskClassName = classOptions.value.find((c: any) => c.id === taskClassId)?.name || `班级#${taskClassId}`
      tasks.value.unshift({
        id: res.task_ids[i],
        classId: taskClassId,
        className: taskClassName,
        reportType: 'class_moral',
        state: 'PENDING',
        progress: 0,
        statusText: `批量任务 ${i + 1}/${res.task_ids.length}，排队中...`,
        createdAt: new Date(),
      })
    }
    ElMessage.success(`全年级 ${res.total_classes} 个班级的报告任务已提交`)
    startPolling()
  } catch {
    ElMessage.error('批量提交失败，请重试')
  } finally {
    batchExporting.value = false
  }
}

// ═══════════════════════════════════════════════════
// Polling Engine
// ═══════════════════════════════════════════════════

function startPolling() {
  if (pollTimer) return
  pollingActive.value = true
  pollCount.value = 0
  pollTimer = setInterval(async () => {
    pollCount.value++
    const pending = tasks.value.filter(
      (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
    )
    if (pending.length === 0 || pollCount.value >= MAX_POLL_COUNT) {
      stopPolling()
      return
    }
    const updates = await Promise.allSettled(
      pending.map((t) => getTaskStatus(t.id).catch(() => null)),
    )
    let allDone = true
    updates.forEach((result, idx) => {
      const task = pending[idx]
      const status = result.status === 'fulfilled' ? result.value : null
      if (!status) {
        allDone = false
        return
      }
      task.state = status.state
      task.progress = status.progress || 0
      task.statusText = status.status_text || taskStateLabel(status.state)
      if (status.state === 'SUCCESS' && status.result) {
        task.result = status.result
      }
      if (status.state === 'FAILURE') {
        task.error = status.error || '未知错误'
      }
      if (status.state === 'PENDING' || status.state === 'PROGRESS') {
        allDone = false
      }
    })
    if (allDone) {
      stopPolling()
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollingActive.value = false
}

async function refreshAllTasks() {
  const pending = tasks.value.filter(
    (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
  )
  if (pending.length === 0) {
    ElMessage.info('没有需要刷新的活跃任务')
    return
  }
  pollingActive.value = true
  const updates = await Promise.allSettled(
    pending.map((t) => getTaskStatus(t.id).catch(() => null)),
  )
  updates.forEach((result, idx) => {
    const task = pending[idx]
    const status = result.status === 'fulfilled' ? result.value : null
    if (!status) return
    task.state = status.state
    task.progress = status.progress || 0
    task.statusText = status.status_text || taskStateLabel(status.state)
    if (status.state === 'SUCCESS' && status.result) {
      task.result = status.result
    }
    if (status.state === 'FAILURE') {
      task.error = status.error || '未知错误'
    }
  })
  pollingActive.value = false
  ElMessage.success(`已刷新 ${pending.length} 个任务状态`)
}

// ═══════════════════════════════════════════════════
// Task Management
// ═══════════════════════════════════════════════════

function downloadReport(task: TaskTracker) {
  if (!task.result?.download_url) {
    ElMessage.warning('下载链接不可用')
    return
  }
  window.open(task.result.download_url, '_blank')
  ElMessage.success(`开始下载: ${task.result.filename}`)
}

function removeTask(taskId: string) {
  tasks.value = tasks.value.filter((t) => t.id !== taskId)
}

async function clearCompleted() {
  try {
    await ElMessageBox.confirm(
      `确定清除全部 ${completedTasks.value.length} 条已完成任务吗？`,
      '确认清除',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
    tasks.value = tasks.value.filter(
      (t) => t.state === 'PENDING' || t.state === 'PROGRESS',
    )
    ElMessage.success('已完成任务已清除')
  } catch {
    // cancelled
  }
}

// ═══════════════════════════════════════════════════
// Demo Mode
// ═══════════════════════════════════════════════════

function demoTask() {
  const classId = singleForm.value.class_id || 1
  const className =
    classOptions.value.find((c) => c.id === classId)?.name || '七(1)班'
  const demoTaskId = `demo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const initialTracker: TaskTracker = {
    id: demoTaskId,
    classId,
    className,
    reportType: singleForm.value.report_type,
    state: 'PENDING',
    progress: 0,
    statusText: '任务已提交 (Demo)',
    createdAt: new Date(),
  }
  tasks.value.unshift(initialTracker)
  simulateTaskProgress(
    demoTaskId,
    classId,
    (tracker) => {
      const idx = tasks.value.findIndex((t) => t.id === demoTaskId)
      if (idx >= 0) {
        tasks.value[idx] = { ...tasks.value[idx], ...tracker }
      }
    },
    (tracker) => {
      const idx = tasks.value.findIndex((t) => t.id === demoTaskId)
      if (idx >= 0) {
        tasks.value[idx] = { ...tasks.value[idx], ...tracker }
      }
      ElMessage.success('Demo: 报告已生成，可点击下载')
    },
  )
}

// ═══════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════

function formatElapsed(date: Date): string {
  const elapsed = Math.floor((Date.now() - date.getTime()) / 1000)
  if (elapsed < 60) return `${elapsed}秒前`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}分钟前`
  return `${Math.floor(elapsed / 3600)}小时前`
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function handleResize() {
  riskChart?.resize()
}

// ═══════════════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════════════

onMounted(async () => {
  // Load class/grade options for PDF export
  try {
    const gradesRes: any = await getGrades()
    const gradesList = gradesRes?.items ?? (Array.isArray(gradesRes) ? gradesRes : [])
    gradeOptions.value = gradesList.map((g: any) => ({ id: g.id, name: g.name }))

    const classesRes: any = await getClasses()
    const classesList = classesRes?.items ?? (Array.isArray(classesRes) ? classesRes : [])
    classOptions.value = classesList.map((c: any) => ({ id: c.id, name: c.name, grade_id: c.grade_id }))
  } catch {
    classOptions.value = getDemoClasses()
    gradeOptions.value = getDemoGrades()
  }

  if (classOptions.value.length > 0) {
    singleForm.value.class_id = classOptions.value[0].id
  }
  if (gradeOptions.value.length > 0) {
    batchForm.value.grade_id = gradeOptions.value[0].id
  }

  // Load RDI whitepaper data (default Tab 1)
  if (isBatchRole.value) {
    loadRdiSummary()
  } else {
    loadClassReport()
  }

  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  stopPolling()
  window.removeEventListener('resize', handleResize)
  riskChart?.dispose()
  riskChart = null
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════ */
/* Container & Dark Theme Base                          */
/* ═══════════════════════════════════════════════════ */

.reports-console {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0d1117;
  color: #c9d1d9;
}

/* ── Page Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #f0f6fc;
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-subtitle {
  font-size: 13px;
  color: #6e7681;
  margin-top: 4px;
  display: block;
}

/* ═══════════════════════════════════════════════════ */
/* Tabs                                                 */
/* ═══════════════════════════════════════════════════ */

.reports-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px 0;
}

.reports-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: #30363d;
}

.reports-tabs :deep(.el-tabs__item) {
  color: #8b949e;
}

.reports-tabs :deep(.el-tabs__item.is-active) {
  color: #58a6ff;
}

.reports-tabs :deep(.el-tabs__item:hover) {
  color: #58a6ff;
}

.reports-tabs :deep(.el-tabs__active-line) {
  background-color: #58a6ff;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* ═══════════════════════════════════════════════════ */
/* Stat Cards                                           */
/* ═══════════════════════════════════════════════════ */

.stat-row {
  margin-bottom: 12px;
}

.stat-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.2s;
}

.stat-card:hover {
  border-color: #484f58;
}

.stat-label {
  font-size: 12px;
  color: #6e7681;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #f0f6fc;
  line-height: 1.2;
}

.stat-value.text-md {
  font-size: 16px;
  font-weight: 600;
}

.stat-total .stat-value { color: #f0f6fc; }
.stat-red .stat-value { color: #f85149; }
.stat-yellow .stat-value { color: #d29922; }
.stat-green .stat-value { color: #3fb950; }
.stat-blue .stat-value { color: #58a6ff; }

/* ═══════════════════════════════════════════════════ */
/* Panel Cards                                          */
/* ═══════════════════════════════════════════════════ */

.panel-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f6fc;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.panel-header .panel-title {
  margin-bottom: 0;
}

/* ═══════════════════════════════════════════════════ */
/* Chart                                                */
/* ═══════════════════════════════════════════════════ */

.chart-row {
  margin-bottom: 12px;
}

.chart-container {
  width: 100%;
  height: 280px;
}

/* ═══════════════════════════════════════════════════ */
/* Dark Table Override                                  */
/* ═══════════════════════════════════════════════════ */

.dark-table {
  background: transparent !important;
}

.dark-table :deep(.el-table__inner-wrapper) {
  background: transparent !important;
}

.dark-table :deep(th.el-table__cell) {
  background: #161b22 !important;
  color: #8b949e !important;
  border-bottom: 1px solid #30363d !important;
  font-weight: 600;
}

.dark-table :deep(td.el-table__cell) {
  background: transparent !important;
  color: #c9d1d9 !important;
  border-bottom: 1px solid #21262d !important;
}

.dark-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: #21262d !important;
}

.dark-table :deep(.el-table__row--striped > td.el-table__cell) {
  background: #0d1117 !important;
}

.dark-table :deep(.el-table__row--striped:hover > td.el-table__cell) {
  background: #21262d !important;
}

.dark-table :deep(.el-table__empty-block) {
  background: transparent !important;
}

.dark-table :deep(.el-table__body-wrapper) {
  background: transparent !important;
}

.dark-table :deep(.el-scrollbar) {
  background: transparent !important;
}

.dark-table :deep(.el-table__body-wrapper .el-scrollbar__wrap) {
  background: transparent !important;
}

/* ── Number Colors ── */
.num-red {
  color: #f85149;
  font-weight: 600;
}

.num-yellow {
  color: #d29922;
  font-weight: 600;
}

.rdi-score {
  color: #f85149;
  font-weight: 700;
  font-size: 14px;
}

/* ═══════════════════════════════════════════════════ */
/* Summary Cards (ClassTeacher)                         */
/* ═══════════════════════════════════════════════════ */

.summary-row {
  margin-bottom: 12px;
}

.summary-card {
  min-height: 200px;
}

.summary-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #21262d;
}

.summary-item:last-child {
  border-bottom: none;
}

.summary-label {
  font-size: 13px;
  color: #6e7681;
}

.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
}

.warning-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ═══════════════════════════════════════════════════ */
/* PDF Export Workbench (Tab 2)                         */
/* ═══════════════════════════════════════════════════ */

.workbench-body {
  flex: 1;
  overflow: hidden;
}

.export-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.export-card {
  margin-bottom: 0;
}

.export-form {
  margin-top: 4px;
}

.export-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6e7681;
  line-height: 1.6;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid #21262d;
}

.task-list-card {
  height: calc(100vh - 220px);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ── Progress Section ── */
.progress-section {
  margin-bottom: 16px;
}

.progress-card {
  padding: 12px;
  margin-bottom: 10px;
  background: #0d1117;
  border-radius: 8px;
  border: 1px solid #21262d;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #c9d1d9;
}

.progress-class {
  font-weight: 600;
}

.progress-type {
  color: #6e7681;
  font-size: 12px;
}

.progress-pct {
  font-size: 14px;
  font-weight: 700;
  color: #58a6ff;
}

.progress-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.progress-text {
  font-size: 12px;
  color: #6e7681;
}

.progress-time {
  font-size: 12px;
  color: #484f58;
}

/* ── Completed Section ── */
.completed-section {
  flex: 1;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #21262d;
}

.filename-text {
  font-size: 13px;
  color: #58a6ff;
  cursor: pointer;
}

.filename-text:hover {
  text-decoration: underline;
}

.error-text {
  font-size: 13px;
  color: #f85149;
}

/* ═══════════════════════════════════════════════════ */
/* Element Plus Dark Overrides                           */
/* ═══════════════════════════════════════════════════ */

/* Radio buttons */
:deep(.el-radio-group) {
  width: 100%;
}

:deep(.el-radio-button) {
  flex: 1;
}

:deep(.el-radio-button__inner) {
  width: 100%;
  text-align: center;
  background: #21262d;
  border-color: #30363d;
  color: #c9d1d9;
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #fff;
}

/* Form labels */
:deep(.el-form-item__label) {
  color: #8b949e;
}

/* Select */
:deep(.el-select__wrapper) {
  background: #0d1117;
  box-shadow: 0 0 0 1px #30363d inset;
}

:deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px #484f58 inset;
}

:deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px #58a6ff inset;
}

:deep(.el-select__placeholder) {
  color: #6e7681;
}

/* Empty */
:deep(.el-empty__description p) {
  color: #6e7681;
}

/* Loading */
:deep(.el-loading-mask) {
  background: rgba(13, 17, 23, 0.8);
}

/* Card (for any remaining el-card usage) */
:deep(.el-card) {
  background: #161b22;
  border: 1px solid #30363d;
  color: #c9d1d9;
}

:deep(.el-card__header) {
  border-bottom: 1px solid #30363d;
}

/* Progress bar */
:deep(.el-progress-bar__outer) {
  background: #21262d;
}
</style>
