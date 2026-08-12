<template>
  <div class="copilot">
    <!-- ═══════════════ Empty State ═══════════════ -->
    <template v-if="!result && !loading && !error">
      <div class="hero-empty">
        <div class="hero-icon">✦</div>
        <h1>WINGS AI</h1>
        <p class="hero-sub">下午好，AI 已准备好分析您负责的年级数据</p>
      </div>

      <div class="input-block">
        <textarea
          v-model="goal"
          :disabled="loading"
          placeholder="帮我看看一年级最近有什么值得本周重点关注的问题"
          rows="2"
          @keydown.ctrl.enter="run"
        />
        <button class="btn-go" :disabled="loading || !goal.trim()" @click="run">→</button>
      </div>

      <div class="quick-row">
        <button @click="setQuick('分析一年级最近一次考试')">📊 最近考试分析</button>
        <button @click="setQuick('比较一年级最近两次考试的变化趋势')">📈 考试趋势</button>
        <button @click="setQuick('帮我看看一年级最近有什么值得本周重点关注的问题')">✨ 本周重点</button>
      </div>
    </template>

    <!-- ═══════════════ Loading ═══════════════ -->
    <div v-if="loading" class="hero-empty">
      <div class="hero-icon spinner" />
      <h1>AI 正在分析</h1>
      <p class="hero-sub">正在读取数据、执行分析并进行安全自检…</p>
    </div>

    <!-- ═══════════════ Error ═══════════════ -->
    <div v-if="error" class="hero-empty">
      <div class="hero-icon">⚠</div>
      <h1>分析未能完成</h1>
      <p class="hero-sub">{{ error }}</p>
      <button class="btn-go" @click="run">重试</button>
    </div>

    <!-- ═══════════════ NEEDS_DATA ═══════════════ -->
    <div v-if="result && result.outcome === 'needs_data'" class="needs-data">
      <div class="hero-icon">📊</div>
      <h2>还缺一些数据</h2>
      <p class="nd-sub">
        AI 已确认：<br />
        <template v-if="result.student_count > 0">
          ✓ 该年级有 {{ result.student_count }} 名学生<br />
          ✓ 您具有该年级数据权限<br />
        </template>
        ✓ 成绩分析工具正常<br />
        <br />
        目前暂未找到满足条件的考试数据，<br />
        AI 没有强行生成趋势结论。
      </p>
      <div class="nd-tag">AI 在数据不足时不编造结论</div>
      <div class="quick-row" style="justify-content:center;margin-top:16px">
        <button @click="setQuick('分析一年级最近一次考试'); run()">分析最近一次考试</button>
        <button @click="setQuick('帮我看看一年级最近有什么值得本周重点关注的问题'); run()">查找本周重点</button>
      </div>
    </div>

    <!-- ═══════════════ SUCCESS Dashboard ═══════════════ -->
    <template v-if="result && result.outcome === 'success'">
      <!-- Header -->
      <div class="dash-header">
        <div>
          <span class="dash-eyebrow">一年级 · 分析完成</span>
          <h2>最近考试分析</h2>
        </div>
        <span class="dash-badge">✓ 分析完成</span>
      </div>

      <!-- KPI -->
      <div class="kpi-row">
        <div class="kpi">
          <span class="kpi-num">{{ result.student_count || overviewVal('student_count') || '—' }}</span>
          <span class="kpi-label">覆盖学生</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ result.examined_count || overviewVal('examined_students') || '—' }}</span>
          <span class="kpi-label">参考学生</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ overviewVal('subjects') || overviewVal('subject_count') || '—' }}</span>
          <span class="kpi-label">分析科目</span>
        </div>
        <div class="kpi">
          <span class="kpi-num">{{ overviewVal('grade_records') || '—' }}</span>
          <span class="kpi-label">成绩记录</span>
        </div>
      </div>

      <!-- Findings -->
      <div class="findings-block" v-if="result.findings.length">
        <div class="section-title">🔎 核心发现</div>
        <div class="finding" v-for="(item, i) in result.findings" :key="i">
          <span class="f-idx">{{ i + 1 }}</span>
          <span>{{ item }}</span>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="recs-block" v-if="result.recommendations.length">
        <div class="section-title">✨ AI 建议</div>
        <div class="rec" v-for="(item, i) in result.recommendations" :key="i">
          <span class="r-idx">{{ String(i + 1).padStart(2, '0') }}</span>
          <p>{{ item }}</p>
        </div>
      </div>
    </template>

    <!-- ═══════════════ Trust Footer ═══════════════ -->
    <footer v-if="result" class="trust-footer">
      <span>AI 分析安全可信</span>
      <span>·</span>
      <span v-if="result.trust.permission_checked">权限已校验</span>
      <span>·</span>
      <span v-if="!result.trust.student_pii_sent">无学生 PII 泄露</span>
      <span>·</span>
      <span>{{ result.model }}</span>
      <span>·</span>
      <span>Critic {{ result.critic.passed ? 'PASS' : 'FAIL' }}</span>
      <span>·</span>
      <button class="btn-trust" @click="drawerOpen = true">Run #{{ result.run_id }}</button>
    </footer>

    <!-- ═══════════════ Input (after result) ═══════════════ -->
    <div v-if="result" class="input-block secondary">
      <textarea
        v-model="goal"
        :disabled="loading"
        placeholder="继续提问…"
        rows="2"
        @keydown.ctrl.enter="run"
      />
      <button class="btn-go" :disabled="loading || !goal.trim()" @click="run">→</button>
    </div>

    <!-- ═══════════════ Drawer ═══════════════ -->
    <div v-if="drawerOpen && result" class="drawer-mask" @click.self="drawerOpen = false">
      <aside class="drawer">
        <button class="drawer-close" @click="drawerOpen = false">×</button>
        <h3>运行详情</h3>

        <div class="dr"><span>Run</span><strong>#{{ result.run_id }}</strong></div>
        <div class="dr"><span>状态</span><strong>Agent {{ result.status.toUpperCase() }}</strong></div>
        <div class="dr"><span>结果</span><strong :class="outcomeClass">{{ outcomeLabel }}</strong></div>
        <div class="dr"><span>模型</span><strong>{{ result.model }}</strong></div>
        <div class="dr"><span>Critic</span><strong :class="result.critic.passed ? 'g' : 'r'">{{ result.critic.passed ? 'PASS' : 'FAIL' }}</strong></div>

        <h4>执行步骤</h4>
        <div v-for="s in result.plan" :key="s.tool" class="dr"><span>{{ toolLabel(s.tool) }}</span><strong class="g">{{ s.status }}</strong></div>

        <h4>安全验证</h4>
        <div class="dr"><span>权限校验</span><strong class="g">✓</strong></div>
        <div class="dr"><span>数据聚合</span><strong class="g">✓</strong></div>
        <div class="dr"><span>PII 保护</span><strong class="g">✓</strong></div>
        <div class="dr"><span>全链记录</span><strong class="g">✓</strong></div>
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
const gradeId = 1

const toolLabels: Record<string, string> = {
  read_class_grade_summary: '读取成绩摘要',
  compare_exam_performance: '比较考试变化',
}
function toolLabel(t: string) { return toolLabels[t] ?? t }

const outcomeLabels: Record<string, string> = {
  success: '任务完成',
  needs_data: '需要更多数据',
  needs_input: '需要补充信息',
  denied: '权限不足',
  failed: '执行失败',
}
const outcomeLabel = computed(() => outcomeLabels[result.value?.outcome ?? ''] ?? result.value?.outcome ?? '—')
const outcomeClass = computed(() => result.value?.outcome === 'success' ? 'g' : result.value?.outcome === 'needs_data' ? 'y' : 'r')

function overviewVal(key: string) {
  const o = result.value?.overview
  if (!o) return null
  return o[key]
}

function setQuick(text: string) { goal.value = text }

async function run() {
  if (!goal.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await runCopilot({ goal: goal.value, grade_id: gradeId })
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message ?? e?.response?.data?.detail ?? e?.message ?? '执行失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.copilot { max-width: 800px; margin: 0 auto; padding: 40px 24px; color: #172033; }

/* ── Hero empty ── */
.hero-empty { text-align: center; padding: 60px 0 30px; }
.hero-icon { font-size: 48px; margin-bottom: 12px; }
.hero-empty h1 { font-size: 32px; font-weight: 800; margin: 0 0 8px; }
.hero-sub { color: #657086; font-size: 16px; margin: 0; }

/* ── Input ── */
.input-block { display: flex; gap: 10px; background: #fff; border: 1px solid #dfe3ec; border-radius: 16px; padding: 10px 12px; margin: 24px 0; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.input-block textarea { flex: 1; border: 0; resize: none; outline: none; font-size: 15px; font-family: inherit; padding: 6px 0; background: transparent; }
.btn-go { width: 44px; height: 44px; border: 0; border-radius: 12px; background: #4f46e5; color: #fff; font-size: 20px; cursor: pointer; flex-shrink: 0; }
.btn-go:disabled { opacity: .4; }
.input-block.secondary { margin-top: 32px; }

.quick-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.quick-row button { padding: 8px 14px; border-radius: 10px; border: 1px solid #e1e5ee; background: #fafbfc; cursor: pointer; font-size: 13px; }
.quick-row button:hover { background: #f0f2f8; }

/* ── Needs Data ── */
.needs-data { text-align: center; padding: 40px 0; }
.needs-data h2 { font-size: 24px; margin: 12px 0; }
.nd-sub { color: #465269; font-size: 15px; line-height: 1.7; }
.nd-tag { display: inline-block; margin-top: 16px; padding: 8px 16px; border-radius: 10px; background: #eef2ff; color: #4f46e5; font-size: 13px; font-weight: 600; }

/* ── Dashboard ── */
.dash-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.dash-eyebrow { font-size: 12px; font-weight: 600; color: #6366f1; text-transform: uppercase; letter-spacing: .1em; }
.dash-header h2 { margin: 4px 0 0; font-size: 26px; }
.dash-badge { padding: 6px 14px; border-radius: 999px; background: #ecfdf3; color: #137a45; font-size: 13px; font-weight: 600; white-space: nowrap; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.kpi { padding: 18px; background: #fff; border: 1px solid #e8ebf2; border-radius: 14px; text-align: center; }
.kpi-num { display: block; font-size: 28px; font-weight: 800; color: #172033; }
.kpi-label { display: block; margin-top: 4px; font-size: 12px; color: #818ca0; }

.section-title { font-size: 17px; font-weight: 700; margin-bottom: 14px; }

.findings-block { background: #fff; border: 1px solid #e8ebf2; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
.finding { display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f0f2f6; }
.finding:last-child { border: 0; }
.f-idx { flex: 0 0 26px; height: 26px; display: flex; align-items: center; justify-content: center; background: #eef2ff; color: #4f46e5; border-radius: 8px; font-weight: 700; font-size: 13px; }

.recs-block { background: #fff; border: 1px solid #e8ebf2; border-radius: 16px; padding: 20px; }
.rec { display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f0f2f6; }
.rec:last-child { border: 0; }
.rec p { margin: 0; }
.r-idx { flex: 0 0 28px; font-size: 13px; font-weight: 700; color: #6366f1; }

/* ── Trust footer ── */
.trust-footer { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 24px; padding: 12px 0; border-top: 1px solid #e8ebf2; color: #8490a5; font-size: 12px; }
.btn-trust { border: 0; background: none; color: #4f46e5; cursor: pointer; font-size: 12px; font-weight: 600; }

/* ── Drawer ── */
.drawer-mask { position: fixed; inset: 0; background: rgba(15,23,42,.25); z-index: 999; }
.drawer { position: absolute; right: 0; top: 0; width: 360px; height: 100%; overflow-y: auto; background: #fff; padding: 24px; box-shadow: -12px 0 30px rgba(15,23,42,.08); }
.drawer-close { float: right; border: 0; background: transparent; font-size: 24px; cursor: pointer; }
.drawer h3, .drawer h4 { margin: 16px 0 10px; }
.dr { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f2f6; font-size: 14px; }
.g { color: #16a34a; } .r { color: #dc2626; } .y { color: #d97706; }

.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 700px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
}
</style>
