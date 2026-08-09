<template>
  <div class="rdi-panel-container">
    <div class="panel-header">
      <div class="header-title">
        <span class="pulse-icon">🚨</span>
        <h3>RDI 跨周期学业危机红黄灯预警流水盘</h3>
      </div>
      <button @click="handleTriggerRdi" :disabled="analyzing" class="analysis-btn">
        {{ analyzing ? 'RDI 逆向追溯中...' : '一键强制点火 RDI 引擎' }}
      </button>
    </div>

    <div class="alerts-grid">
      <div v-if="loading" class="skeleton-loader">正在加载全校危重学生资产...</div>
      <div v-else-if="alerts.length === 0" class="empty-alerts">
        大盘晴空万里，暂未拦截到学业坍塌的红黄灯危重样本。
      </div>

      <div
        v-else
        v-for="alert in alerts"
        :key="alert.id"
        class="alert-card"
        :class="alert.risk_level"
      >
        <div class="card-badge">{{ alert.risk_level === 'red' ? '重度红灯' : '中度黄灯' }}</div>
        <div class="card-body">
          <div class="meta-row">
            <span>学生编号: <strong>{{ alert.student_id }}</strong></span>
            <span>大考ID: {{ alert.exam_id }}</span>
            <span class="risk-type-tag">{{ alert.risk_type }}</span>
          </div>
          <p class="trigger-reason">{{ alert.trigger_reason }}</p>
          <div class="card-footer">
            <span class="time-stamp">{{ formatTime(alert.created_at) }}</span>
            <button @click="openDrawer(alert)" class="drawer-trigger-btn">
              穿透三层血缘 &amp; 调阅 AI 处方 →
            </button>
          </div>
        </div>
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      title="RDI (Risk-Data-Lineage) 数字化血缘透视面板"
      size="55%"
      direction="rtl"
      custom-class="rdi-dark-drawer"
    >
      <div v-if="selectedAlert" class="drawer-content">
        <!-- 三层 DAG 拓扑 -->
        <div class="section-title">📊 RDI 根源性三层数据血缘有向图 (DAG)</div>
        <div class="dag-container">
          <div class="dag-layer">
            <div class="layer-name">Layer 3: 异构数据源</div>
            <div
              v-for="node in getLayerNodes('source_ingestion')"
              :key="node.id"
              class="dag-node src-node"
            >
              <div class="node-title">教务接入锚点</div>
              <div class="node-meta">班级ID: {{ node.data.admin_class_id }}</div>
              <div class="node-engine">{{ node.data.ingestion_engine }}</div>
            </div>
          </div>

          <div class="dag-arrow">➔</div>

          <div class="dag-layer">
            <div class="layer-name">Layer 2: 级联多维指标</div>
            <div
              v-for="node in getLayerNodes('aggregation_metrics')"
              :key="node.id"
              class="dag-node agg-node"
            >
              <div class="node-title">{{ getSubjectLabel(node.id) }}</div>
              <div class="node-score">原始分: <span>{{ node.data.raw_score }}</span></div>
              <div class="node-z">
                Z-Score:
                <span :class="Number(node.data.computed_z_score) <= -1.5 ? 'text-red' : 'text-orange'">
                  {{ node.data.computed_z_score }}
                </span>
              </div>
              <div class="node-rank">年级排名: {{ node.data.cohort_rank || '暂无' }}</div>
            </div>
          </div>

          <div class="dag-arrow">➔</div>

          <div class="dag-layer">
            <div class="layer-name">Layer 1: 风险洞察</div>
            <div
              v-for="node in getLayerNodes('risk_insight')"
              :key="node.id"
              class="dag-node insight-node"
            >
              <div class="node-title">{{ node.label }}</div>
              <div class="node-meta">类型: {{ node.data.risk_type }}</div>
              <div class="node-status">状态: ACTIVE</div>
            </div>
          </div>
        </div>

        <!-- AI 处方区 -->
        <div class="section-title">🤖 DeepSeek 引擎定向赋能精细化处方</div>
        <div class="prescriptions-wrapper">
          <div v-if="prescriptionsLoading" class="pres-loader">正在调阅大模型数字资产...</div>
          <div v-else-if="prescriptions.length === 0" class="empty-pres">
            该预警血缘上未发现已落盘的 AI 处方，请触发引擎生成。
          </div>
          <div v-else v-for="pres in prescriptions" :key="pres.id" class="pres-card">
            <div class="pres-card-header">
              <span class="subject-tag">{{ pres.subject_code.toUpperCase() }} 学科诊断</span>
              <span class="pres-stat">诊断锚点 Z分: {{ pres.z_score }}</span>
            </div>
            <div class="pres-block">
              <h5>📉 知识断层与归因诊断 (Weakness Analysis)</h5>
              <p>{{ pres.weakness_analysis }}</p>
            </div>
            <div class="pres-block">
              <h5>💊 针对性补偿行动处方 (Action Prescription)</h5>
              <p class="whitespace-pre-line">{{ pres.action_prescription }}</p>
            </div>
            <div v-if="pres.model_metadata" class="pres-meta">
              <span>模型: {{ pres.model_metadata.model || 'N/A' }}</span>
              <span v-if="pres.model_metadata.total_tokens">
                | Token: {{ pres.model_metadata.total_tokens }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getRiskAlerts,
  getPrescriptions,
  triggerRdiAnalysis,
  type RiskAlert,
  type Prescription,
} from '@/api/dataAdapter'

const props = defineProps<{
  examId: number
}>()

const loading = ref(false)
const analyzing = ref(false)
const prescriptionsLoading = ref(false)
const drawerVisible = ref(false)
const alerts = ref<RiskAlert[]>([])
const prescriptions = ref<Prescription[]>([])
const selectedAlert = ref<RiskAlert | null>(null)

const SUBJECT_MAP: Record<string, string> = {
  chinese: '语文', math: '数学', english: '英语',
  physics: '物理', history: '历史', chemistry: '化学',
  biology: '生物', politics: '政治', geography: '地理',
}

const fetchAlerts = async () => {
  if (!props.examId) return
  loading.value = true
  try {
    const res = await getRiskAlerts(props.examId)
    if (res && res.status === 'success') {
      alerts.value = res.alerts || []
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '未知中断'
    ElMessage.error(`拉取RDI危机大盘失败: ${detail}`)
  } finally {
    loading.value = false
  }
}

const handleTriggerRdi = async () => {
  if (!props.examId) return
  analyzing.value = true
  try {
    const res = await triggerRdiAnalysis(props.examId)
    if (res && res.status === 'success') {
      const rdiData = res.data || {}
      const aiData = res.ai_prescriptions || {}
      const alertCount = rdiData.alerts_triggered || 0
      const presCount = aiData.prescriptions_generated || 0
      ElMessage.success(
        `RDI 三层血缘追溯与 AI 处方全链路落盘成功！${alertCount} 条预警 → ${presCount} 条处方`
      )
      await fetchAlerts()
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '未知中断'
    ElMessage.error(`RDI 自动机熔断: ${detail}`)
  } finally {
    analyzing.value = false
  }
}

const fetchPres = async (alertId: number) => {
  prescriptionsLoading.value = true
  try {
    const res = await getPrescriptions(alertId)
    if (res && res.status === 'success') {
      prescriptions.value = res.prescriptions || []
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '未知中断'
    ElMessage.error(`调阅 AI 处方失败: ${detail}`)
  } finally {
    prescriptionsLoading.value = false
  }
}

const openDrawer = (alert: RiskAlert) => {
  selectedAlert.value = alert
  drawerVisible.value = true
  prescriptions.value = []
  fetchPres(alert.id)
}

const getLayerNodes = (layerName: string) => {
  if (!selectedAlert.value?.lineage_graph?.nodes) return []
  return selectedAlert.value.lineage_graph.nodes.filter((n) => n.layer === layerName)
}

const getSubjectLabel = (nodeId: string): string => {
  const parts = nodeId.split('_')
  const code = parts[parts.length - 1]
  return SUBJECT_MAP[code] || code
}

const formatTime = (timeStr: string | null): string => {
  if (!timeStr) return ''
  return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
}

watch(
  () => props.examId,
  (newId) => {
    if (newId) fetchAlerts()
  }
)

onMounted(() => {
  if (props.examId) fetchAlerts()
})
</script>

<style scoped>
.rdi-panel-container {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 24px;
  margin-top: 24px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
  padding-bottom: 16px;
  margin-bottom: 20px;
}
.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-title h3 {
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0;
}
.pulse-icon {
  animation: pulse-red 2s infinite ease-in-out;
}
.analysis-btn {
  background: #238636;
  border: 1px solid rgba(240, 246, 252, 0.1);
  color: #ffffff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.analysis-btn:hover {
  background: #2ea043;
}
.analysis-btn:disabled {
  background: #21262d;
  color: #8b949e;
  cursor: not-allowed;
}

.alerts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
  gap: 16px;
}
.alert-card {
  background: #0d1117;
  border-radius: 8px;
  border-left: 4px solid #30363d;
  padding: 16px;
  position: relative;
  transition: transform 0.2s;
}
.alert-card:hover {
  transform: translateY(-2px);
}
.alert-card.red {
  border-left-color: #f85149;
}
.alert-card.yellow {
  border-left-color: #d29922;
}

.card-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  font-size: 11px;
  font-weight: bold;
  padding: 2px 8px;
  border-radius: 12px;
}
.red .card-badge {
  background: rgba(248, 81, 73, 0.15);
  color: #f85149;
}
.yellow .card-badge {
  background: rgba(210, 153, 34, 0.15);
  color: #d29922;
}

.meta-row {
  display: flex;
  gap: 20px;
  color: #8b949e;
  font-size: 13px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.meta-row strong {
  color: #58a6ff;
}
.risk-type-tag {
  padding: 1px 8px;
  border-radius: 4px;
  background: #21262d;
  color: #6e7681;
  font-size: 11px;
}
.trigger-reason {
  color: #c9d1d9;
  font-size: 14px;
  line-height: 1.5;
  margin: 8px 0 16px 0;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid #21262d;
  padding-top: 12px;
}
.time-stamp {
  color: #6e7681;
  font-size: 12px;
}
.drawer-trigger-btn {
  background: transparent;
  border: none;
  color: #58a6ff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.drawer-trigger-btn:hover {
  text-decoration: underline;
}

/* DAG 拓扑 */
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #58a6ff;
  background: rgba(88, 166, 255, 0.05);
  padding: 8px 12px;
  border-left: 3px solid #58a6ff;
  margin: 24px 0 16px 0;
  border-radius: 0 4px 4px 0;
}
.dag-container {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  background: #0d1117;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #30363d;
  gap: 8px;
}
.dag-layer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-width: 0;
}
.layer-name {
  font-size: 11px;
  color: #6e7681;
  text-align: center;
  text-transform: uppercase;
  margin-bottom: 4px;
  letter-spacing: 0.05em;
}
.dag-node {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
}
.src-node {
  border-top: 3px solid #bc8cff;
}
.agg-node {
  border-top: 3px solid #2dd4bf;
}
.insight-node {
  border-top: 3px solid #f85149;
}

.node-title {
  font-weight: 600;
  color: #e6edf3;
  margin-bottom: 4px;
}
.node-meta,
.node-engine,
.node-rank {
  color: #8b949e;
  font-size: 12px;
}
.node-score span {
  color: #e6edf3;
  font-weight: bold;
}
.node-z span {
  font-weight: bold;
}
.text-red {
  color: #f85149;
}
.text-orange {
  color: #d29922;
}

.dag-arrow {
  color: #30363d;
  font-size: 20px;
  align-self: center;
  padding-top: 30px;
}

/* AI 处方 */
.prescriptions-wrapper {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pres-card {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
}
.pres-card-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #21262d;
  padding-bottom: 10px;
  margin-bottom: 12px;
  align-items: center;
}
.subject-tag {
  background: rgba(45, 212, 191, 0.1);
  color: #2dd4bf;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}
.pres-stat {
  color: #8b949e;
  font-size: 12px;
}
.pres-block {
  margin-bottom: 14px;
}
.pres-block h5 {
  color: #c9d1d9;
  font-size: 13px;
  margin: 0 0 6px 0;
}
.pres-block p {
  color: #8b949e;
  font-size: 13px;
  line-height: 1.6;
}
.whitespace-pre-line {
  white-space: pre-line;
  color: #e6edf3 !important;
}
.pres-meta {
  font-size: 11px;
  color: #6e7681;
  border-top: 1px solid #21262d;
  padding-top: 8px;
  display: flex;
  gap: 8px;
}

.skeleton-loader,
.empty-alerts,
.pres-loader,
.empty-pres {
  color: #8b949e;
  font-size: 14px;
  text-align: center;
  padding: 30px;
  width: 100%;
}

@keyframes pulse-red {
  0%,
  100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}

@media (max-width: 900px) {
  .dag-container {
    flex-direction: column;
    gap: 12px;
  }
  .dag-arrow {
    transform: rotate(90deg);
    padding-top: 0;
    text-align: center;
  }
  .alerts-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
.rdi-dark-drawer {
  background-color: #161b22 !important;
  color: #e6edf3 !important;
  border-left: 1px solid #30363d !important;
}
.rdi-dark-drawer .el-drawer__header {
  color: #e6edf3 !important;
  border-bottom: 1px solid #30363d;
  padding-bottom: 16px;
  margin-bottom: 0;
}
.rdi-dark-drawer .el-drawer__close-btn .el-icon {
  color: #8b949e !important;
}
.rdi-dark-drawer .el-drawer__body {
  padding: 20px;
}
</style>
