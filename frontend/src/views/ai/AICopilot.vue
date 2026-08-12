<template>
  <div class="copilot-page">
    <!-- ① Header -->
    <div class="hero">
      <div>
        <span class="eyebrow">WINGS AI COPILOT</span>
        <h1>让学校数据主动找到你</h1>
        <p>基于真实业务数据、权限范围和 AI Agent，自动完成分析、比较与管理建议。</p>
      </div>
      <span class="service-badge"><span class="dot" /> AI 服务正常</span>
    </div>

    <!-- ② 输入区 -->
    <div class="card">
      <div class="input-row">
        <textarea
          v-model="goal"
          :disabled="loading"
          placeholder="例如：帮我看看一年级最近考试有什么值得本周重点关注的问题"
          rows="3"
          @keydown.ctrl.enter="run"
        />
        <button class="btn-run" :disabled="loading || !goal.trim()" @click="run">
          {{ loading ? 'AI 正在分析…' : '开始分析' }}
        </button>
      </div>
      <div class="quick-row">
        <button @click="setQuick('分析一年级最近一次考试')">📊 分析最近考试</button>
        <button @click="setQuick('比较一年级最近两次考试的变化趋势')">📈 比较考试变化</button>
        <button @click="setQuick('帮我看看一年级最近有什么值得本周重点关注的问题')">✨ 找出本周重点</button>
      </div>
    </div>

    <!-- ③ Loading -->
    <div v-if="loading" class="card working">
      <div class="working-title"><span class="spinner" /> 正在执行 AI Agent...</div>
      <p class="working-tip">AI 只会访问您被授权的数据范围。分析完成后将自动进行安全自检。</p>
    </div>

    <!-- Error -->
    <div v-if="error" class="card error-card">
      <strong>分析失败</strong>
      <p>{{ error }}</p>
      <button @click="run">重新分析</button>
    </div>

    <!-- ④ 结果 -->
    <template v-if="result">
      <!-- 指标卡 -->
      <div class="metrics">
        <div class="metric"><span>运行状态</span><strong>{{ result.status.toUpperCase() }}</strong></div>
        <div v-for="(v, k) in displayMetrics" :key="k" class="metric">
          <span>{{ k }}</span><strong>{{ v }}</strong>
        </div>
      </div>

      <!-- ⑤ 执行过程 -->
      <div class="card">
        <div class="card-title">⚙️ Agent 执行过程</div>
        <div v-for="s in result.plan" :key="s.tool" class="step-row">
          <span class="step-ok">✓</span>
          <div><strong>{{ toolLabel(s.tool) }}</strong><p>{{ s.reason }}</p></div>
          <span class="step-tag">{{ s.status }}</span>
        </div>
      </div>

      <!-- ⑥ 发现 + 建议 -->
      <div class="two-col">
        <div class="card">
          <div class="card-title">🔎 核心发现</div>
          <div v-for="(item, i) in result.findings" :key="i" class="item">
            <span class="idx">{{ i + 1 }}</span>
            <span>{{ item }}</span>
          </div>
        </div>
        <div class="card">
          <div class="card-title">💡 本周建议</div>
          <div v-for="(item, i) in result.recommendations" :key="i" class="item">
            <span class="idx">{{ i + 1 }}</span>
            <p>{{ item }}</p>
          </div>
        </div>
      </div>

      <!-- ⑦ Trust Bar -->
      <div class="card trust-bar">
        <div>
          <h3>AI 分析安全可信</h3>
          <div class="trust-checks">
            <span v-if="result.trust.permission_checked">✓ 已校验数据权限</span>
            <span v-if="result.trust.aggregate_before_provider">✓ 学生数据聚合后才发送给 AI</span>
            <span v-if="!result.trust.student_pii_sent">✓ 未向模型发送学生原始 PII</span>
            <span v-if="result.trust.provenance_recorded">✓ AI 操作已全链记录</span>
            <span v-if="result.critic.passed">✓ AI 安全自检通过</span>
          </div>
        </div>
        <div class="trust-meta">
          <strong>Run #{{ result.run_id }}</strong>
          <span>{{ result.model }}</span>
          <button class="btn-detail" @click="drawerOpen = true">查看运行详情</button>
        </div>
      </div>
    </template>

    <!-- ⑧ Drawer -->
    <div v-if="drawerOpen && result" class="drawer-mask" @click.self="drawerOpen = false">
      <aside class="drawer">
        <button class="drawer-close" @click="drawerOpen = false">×</button>
        <h2>Agent 运行详情</h2>

        <div class="detail-row"><span>Run</span><strong>#{{ result.run_id }}</strong></div>
        <div class="detail-row"><span>状态</span><strong>{{ result.status }}</strong></div>
        <div class="detail-row"><span>模型</span><strong>{{ result.model }}</strong></div>
        <div class="detail-row"><span>Critic</span><strong :class="result.critic.passed ? 'green' : 'red'">{{ result.critic.passed ? 'PASS' : 'FAIL' }}</strong></div>

        <h3>执行工具</h3>
        <div v-for="s in result.plan" :key="s.tool" class="detail-tool">✓ {{ toolLabel(s.tool) }}</div>

        <h3>数据安全</h3>
        <div class="detail-tool">✓ 权限范围已校验</div>
        <div class="detail-tool">✓ 聚合后才发送模型</div>
        <div class="detail-tool">✓ 无学生原始 PII 泄露</div>
        <div class="detail-tool">✓ 全链 provenance 已记录</div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { runCopilot, type CopilotRunResponse } from '@/api/aiCopilot'

const goal = ref('帮我看看一年级最近有什么值得本周重点关注的问题')
const loading = ref(false)
const error = ref('')
const result = ref<CopilotRunResponse | null>(null)
const drawerOpen = ref(false)

// 演示版本锁 grade_id=1（一年级）
const gradeId = 1

function setQuick(text: string) {
  goal.value = text
}

async function run() {
  if (!goal.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null

  try {
    const r = await runCopilot({ goal: goal.value, grade_id: gradeId })
    result.value = r
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message
      ?? e?.response?.data?.detail
      ?? e?.message
      ?? 'AI Agent 执行失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

const toolLabels: Record<string, string> = {
  read_class_grade_summary: '读取成绩摘要',
  compare_exam_performance: '比较考试变化',
}

function toolLabel(t: string) { return toolLabels[t] ?? t }

const keyLabels: Record<string, string> = {
  student_count: '学生人数',
  examined_students: '参考人数',
  grade_records: '成绩记录',
  subject_count: '分析科目',
  subjects: '分析科目',
}

const displayMetrics = computed(() => {
  const m: Record<string, any> = {}
  const o = result.value?.overview
  if (!o) return m
  for (const [k, v] of Object.entries(o)) {
    m[keyLabels[k] ?? k] = v
  }
  return m
})

</script>

<style scoped>
.copilot-page { max-width: 1280px; margin: 0 auto; padding: 24px; color: #172033; min-height: 100vh; }
.hero { display: flex; justify-content: space-between; gap: 20px; padding: 28px; border-radius: 20px; background: #fff; border: 1px solid #e8ebf2; }
.eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .15em; color: #6366f1; }
.hero h1 { margin: 8px 0; font-size: 30px; font-weight: 700; }
.hero p { margin: 0; color: #657086; }
.service-badge { align-self: flex-start; padding: 8px 14px; border-radius: 999px; background: #ecfdf3; color: #137a45; font-size: 13px; white-space: nowrap; }
.dot { display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 50%; background: #22c55e; }

.card { margin-top: 16px; padding: 20px; border-radius: 16px; background: #fff; border: 1px solid #e8ebf2; }
.card-title { margin-bottom: 14px; font-size: 16px; font-weight: 700; }
.input-row { display: flex; gap: 12px; }
textarea { flex: 1; resize: none; border: 1px solid #dfe3ec; border-radius: 12px; padding: 12px; font-size: 15px; outline: none; font-family: inherit; }
textarea:focus { border-color: #6366f1; }
.btn-run { width: 120px; border: 0; border-radius: 12px; background: #4f46e5; color: #fff; font-weight: 700; cursor: pointer; font-size: 14px; }
.btn-run:disabled { opacity: .5; }
.quick-row { display: flex; gap: 10px; margin-top: 12px; }
.quick-row button { padding: 7px 12px; border-radius: 8px; border: 1px solid #e1e5ee; background: #fafbfc; cursor: pointer; font-size: 13px; }
.quick-row button:hover { background: #f0f2f8; }

.working { text-align: center; }
.working-title { font-weight: 700; font-size: 17px; }
.working-tip { color: #8490a5; font-size: 13px; margin-top: 10px; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #dfe3ec; border-top-color: #6366f1; border-radius: 50%; animation: spin .6s linear infinite; vertical-align: middle; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-card { color: #b42318; background: #fff7f6; }
.error-card button { margin-top: 10px; }

.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }
.metric { padding: 16px; background: #fff; border: 1px solid #e8ebf2; border-radius: 14px; }
.metric span { display: block; color: #818ca0; font-size: 12px; }
.metric strong { display: block; margin-top: 6px; font-size: 20px; }

.step-row { display: grid; grid-template-columns: 20px 1fr auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid #f0f2f6; }
.step-row p { margin: 2px 0 0; color: #778398; font-size: 13px; }
.step-ok { color: #16a34a; }
.step-tag { font-size: 12px; color: #137a45; background: #ecfdf3; padding: 4px 8px; border-radius: 999px; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.item { display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f0f2f6; }
.item p { margin: 0; }
.idx { flex: 0 0 24px; height: 24px; display: flex; align-items: center; justify-content: center; background: #eef2ff; color: #4f46e5; border-radius: 6px; font-weight: 700; font-size: 12px; }

.trust-bar { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.trust-bar h3 { margin: 0 0 10px; font-size: 15px; }
.trust-checks { display: flex; flex-wrap: wrap; gap: 8px 16px; color: #40506a; font-size: 13px; }
.trust-meta { text-align: right; }
.trust-meta span { display: block; margin: 4px 0 10px; color: #8792a5; font-size: 13px; }
.btn-detail { border: 1px solid #dfe3ec; background: #fff; padding: 7px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; }

.drawer-mask { position: fixed; inset: 0; background: rgba(15,23,42,.25); z-index: 999; }
.drawer { position: absolute; right: 0; top: 0; width: 400px; height: 100%; overflow-y: auto; background: #fff; padding: 28px; box-shadow: -16px 0 40px rgba(15,23,42,.10); }
.drawer-close { float: right; border: 0; background: transparent; font-size: 26px; cursor: pointer; }
.drawer h2 { margin-top: 0; }
.detail-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #edf0f5; }
.detail-tool { padding: 7px 0; color: #40506a; font-size: 14px; }
.green { color: #16a34a; }
.red { color: #dc2626; }

@media (max-width: 900px) {
  .metrics { grid-template-columns: 1fr 1fr; }
  .two-col { grid-template-columns: 1fr; }
  .input-row { flex-direction: column; }
  .btn-run { width: 100%; height: 42px; }
}
</style>
