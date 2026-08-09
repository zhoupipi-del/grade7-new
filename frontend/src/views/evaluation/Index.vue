<template>
  <div class="evaluation-center">
    <!-- ═══════════════════════════════════════ -->
    <!-- Page Header                              -->
    <!-- ═══════════════════════════════════════ -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <el-icon :size="22"><Histogram /></el-icon>
          素质评价中心
        </h2>
        <span class="page-subtitle">五维评价 · 班级排名 · 评分管理 · 流水审计 · 期末综合评价</span>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="small">
          学期: {{ semester }} · 指标: {{ indicatorCount }} 项
        </el-tag>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ -->
    <!-- Tab Navigation                           -->
    <!-- ═══════════════════════════════════════ -->
    <el-tabs v-model="activeTab" type="border-card" class="eval-tabs">
      <!-- ── Tab 1: 学生五维画像 ────────────────── -->
      <el-tab-pane label="学生五维画像" name="portrait">
        <div class="tab-inner">
          <el-row :gutter="16">
            <!-- 左侧: 搜索 & 选择学生 -->
            <el-col :span="8">
              <el-card shadow="never" class="student-selector-card">
                <template #header>
                  <span class="card-title-text">
                    <el-icon><Search /></el-icon> 学生检索
                  </span>
                </template>
                <el-input
                  v-model="studentSearchKeyword"
                  placeholder="输入学生姓名或学号..."
                  clearable
                  size="default"
                  class="mb-3"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>

                <el-select
                  v-model="selectedGradeId"
                  placeholder="选择年级"
                  clearable
                  size="default"
                  style="width: 100%"
                  class="mb-3"
                  @change="onGradeChange"
                >
                  <el-option
                    v-for="g in gradeOptions"
                    :key="g.id"
                    :label="g.name"
                    :value="g.id"
                  />
                </el-select>

                <el-select
                  v-model="selectedClassId"
                  placeholder="按班级筛选"
                  clearable
                  size="default"
                  style="width: 100%"
                  class="mb-3"
                  @change="loadClassStudents"
                >
                  <el-option
                    v-for="c in filteredClassOptions"
                    :key="c.id"
                    :label="c.name"
                    :value="c.id"
                  />
                </el-select>

                <div class="student-list" v-loading="studentsLoading">
                  <el-empty
                    v-if="filteredStudents.length === 0 && !studentsLoading"
                    description="请选择班级或搜索学生"
                    :image-size="60"
                  />
                  <div
                    v-for="s in filteredStudents"
                    :key="s.id"
                    class="student-item"
                    :class="{ active: selectedStudent?.id === s.id }"
                    @click="selectStudent(s)"
                  >
                    <el-avatar :size="32" class="stu-avatar">
                      {{ s.name?.charAt(0) || '?' }}
                    </el-avatar>
                    <div class="stu-info">
                      <span class="stu-name">{{ s.name }}</span>
                      <span class="stu-detail">{{ s.student_no }} · {{ s.class_name }}</span>
                    </div>
                    <span v-if="s.total_score > 0" class="stu-score" :style="{ color: scoreColor(s.total_score) }">
                      {{ s.total_score?.toFixed(1) }}
                    </span>
                    <span v-else class="stu-score no-data">—</span>
                  </div>
                </div>
              </el-card>
            </el-col>

            <!-- 右侧: 五维雷达图 + 评分详情 -->
            <el-col :span="16">
              <el-card shadow="never" v-if="selectedStudent" class="portrait-card">
                <template #header>
                  <div class="card-header-row">
                    <span class="card-title-text">
                      <el-icon><User /></el-icon>
                      {{ selectedStudent.name }} · {{ selectedStudent.class_name }}
                    </span>
                    <el-button size="small" @click="loadStudentScores">刷新数据</el-button>
                  </div>
                </template>

                <el-row :gutter="16">
                  <!-- 雷达图 -->
                  <el-col :span="12">
                    <div class="chart-title-text">五维素质雷达图</div>
                    <div ref="radarChartRef" class="radar-chart-dom" v-loading="scoresLoading" />
                  </el-col>

                  <!-- 分数明细 -->
                  <el-col :span="12">
                    <div class="chart-title-text">维度明细</div>
                    <div v-if="currentScores" class="score-detail-list">
                      <div v-for="dim in dimensions" :key="dim.key" class="score-detail-item">
                        <div class="dim-header">
                          <span class="dim-dot" :style="{ background: dim.color }" />
                          <span class="dim-label">{{ dim.label }}</span>
                          <span class="dim-value" :style="{ color: dim.color }">
                            {{ getDimScore(currentScores, dim.key).toFixed(1) }}
                          </span>
                        </div>
                        <el-progress
                          :percentage="getDimPercent(currentScores, dim.key)"
                          :color="dim.color"
                          :stroke-width="6"
                          :show-text="false"
                        />
                      </div>
                      <el-divider />
                      <div class="total-score-row">
                        <span class="total-label">综合总分</span>
                        <span class="total-value" :style="{ color: scoreColor(currentScores.total_score) }">
                          {{ currentScores.total_score.toFixed(1) }}
                        </span>
                        <span class="total-baseline">/ 基准分 {{ currentScores.base_score }}</span>
                      </div>
                    </div>
                    <el-empty v-else description="暂无评分数据" :image-size="60" />
                  </el-col>
                </el-row>
              </el-card>

              <el-empty
                v-else
                description="请在左侧选择一名学生，查看五维素质画像"
                :image-size="80"
                class="empty-placeholder"
              />
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ── Tab 2: 班级排名 ───────────────────── -->
      <el-tab-pane label="班级排名" name="ranking">
        <div class="tab-inner">
          <el-row :gutter="16">
            <el-col :span="24">
              <el-card shadow="never">
                <template #header>
                  <div class="card-header-row">
                    <span class="card-title-text">
                      <el-icon><Trophy /></el-icon> 班级综合排名
                    </span>
                    <div class="header-actions">
                      <el-select
                        v-model="rankingGradeId"
                        placeholder="选择年级"
                        size="small"
                        style="width: 120px"
                        @change="onRankingGradeChange"
                      >
                        <el-option
                          v-for="g in gradeOptions"
                          :key="g.id"
                          :label="g.name"
                          :value="g.id"
                        />
                      </el-select>
                      <el-select
                        v-model="rankingClassId"
                        placeholder="选择班级"
                        size="small"
                        style="width: 160px"
                        @change="loadClassRanking"
                      >
                        <el-option
                          v-for="c in rankingFilteredClasses"
                          :key="c.id"
                          :label="c.name"
                          :value="c.id"
                        />
                      </el-select>
                    </div>
                  </div>
                </template>

                <!-- 统计概览 -->
                <el-row :gutter="12" class="ranking-stats" v-if="classRanking">
                  <el-col :span="6">
                    <div class="stat-card">
                      <div class="stat-num">{{ classRanking.total_students }}</div>
                      <div class="stat-label">参评人数</div>
                    </div>
                  </el-col>
                  <el-col :span="6">
                    <div class="stat-card">
                      <div class="stat-num" :style="{ color: scoreColor(classRanking.avg_score) }">
                        {{ classRanking.avg_score.toFixed(1) }}
                      </div>
                      <div class="stat-label">平均分</div>
                    </div>
                  </el-col>
                  <el-col :span="6">
                    <div class="stat-card">
                      <div class="stat-num" style="color: #10b981">
                        {{ classRanking.ranking.filter((r: any) => r.total_score >= 90).length }}
                      </div>
                      <div class="stat-label">≥90分</div>
                    </div>
                  </el-col>
                  <el-col :span="6">
                    <div class="stat-card">
                      <div class="stat-num" style="color: #ef4444">
                        {{ classRanking.ranking.filter((r: any) => r.total_score < 60).length }}
                      </div>
                      <div class="stat-label">＜60分</div>
                    </div>
                  </el-col>
                </el-row>

                <el-table
                  :data="classRanking?.ranking || []"
                  v-loading="rankingLoading"
                  size="small"
                  class="ranking-table"
                  :row-class-name="rankingRowClass"
                >
                  <el-table-column label="排名" width="70" align="center">
                    <template #default="{ row }">
                      <el-tag
                        v-if="row.rank <= 3"
                        :type="rankTagType(row.rank)"
                        size="small"
                        effect="dark"
                      >
                        {{ row.rank }}
                      </el-tag>
                      <span v-else>{{ row.rank }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="student_name" label="姓名" width="100" />
                  <el-table-column prop="student_no" label="学号" width="100" />
                  <el-table-column label="总分" width="90" sortable>
                    <template #default="{ row }">
                      <span class="score-highlight" :style="{ color: scoreColor(row.total_score) }">
                        {{ row.total_score.toFixed(1) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column label="道德品质" width="90">
                    <template #default="{ row }">
                      <span>{{ row.moral_score?.toFixed(1) || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="学业水平" width="90">
                    <template #default="{ row }">
                      <span>{{ row.academic_score?.toFixed(1) || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="身心健康" width="90">
                    <template #default="{ row }">
                      <span>{{ row.health_score?.toFixed(1) || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="艺术素养" width="90">
                    <template #default="{ row }">
                      <span>{{ row.art_score?.toFixed(1) || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="社会实践" width="90">
                    <template #default="{ row }">
                      <span>{{ row.social_score?.toFixed(1) || '—' }}</span>
                    </template>
                  </el-table-column>
                </el-table>

                <el-empty
                  v-if="!classRanking && !rankingLoading"
                  description="请选择班级查看排名"
                  :image-size="60"
                />
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ── Tab 3: 评分管理 (指标 + 录分) ────── -->
      <el-tab-pane label="评分管理" name="manage">
        <div class="tab-inner">
          <el-row :gutter="16">
            <!-- 左侧: 指标树 -->
            <el-col :span="12">
              <el-card shadow="never" class="indicator-tree-card">
                <template #header>
                  <div class="card-header-row">
                    <span class="card-title-text">
                      <el-icon><List /></el-icon> 评价指标体系
                    </span>
                    <el-button
                      v-if="isAdmin"
                      type="primary"
                      size="small"
                      :icon="Plus"
                      @click="showIndicatorDialog(null)"
                    >
                      新增指标
                    </el-button>
                  </div>
                </template>

                <div v-loading="indicatorsLoading">
                  <div
                    v-for="group in indicatorGroups"
                    :key="group.dimension"
                    class="indicator-group"
                  >
                    <div class="group-header" :style="{ borderLeftColor: dimensionColor(group.dimension) }">
                      <span>{{ group.dimension_label }}</span>
                      <el-tag size="small" effect="plain">
                        {{ group.items.length }} 项
                      </el-tag>
                    </div>
                    <div v-for="item in group.items" :key="item.id" class="indicator-item">
                      <div class="item-info">
                        <span class="item-name" :class="{ disabled: !item.enabled }">
                          {{ item.name }}
                        </span>
                        <span class="item-meta">
                          权重 {{ item.weight }} · 满分 {{ item.max_score }}
                        </span>
                      </div>
                      <div v-if="isAdmin" class="item-actions">
                        <el-switch
                          v-model="item.enabled"
                          size="small"
                          @change="handleToggleIndicator(item)"
                        />
                        <el-button
                          type="primary"
                          link
                          size="small"
                          :icon="Edit"
                          @click="showIndicatorDialog(item)"
                        />
                        <el-button
                          type="danger"
                          link
                          size="small"
                          :icon="Delete"
                          @click="handleDeleteIndicator(item)"
                        />
                      </div>
                    </div>
                  </div>
                  <el-empty
                    v-if="indicatorGroups.length === 0 && !indicatorsLoading"
                    description="暂无评价指标"
                    :image-size="60"
                  />
                </div>
              </el-card>
            </el-col>

            <!-- 右侧: 录分表单 -->
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <span class="card-title-text">
                    <el-icon><EditPen /></el-icon> 手动录分
                  </span>
                </template>

                <el-form :model="scoreForm" label-width="100px" size="default">
                  <el-form-item label="目标学生">
                    <el-select
                      v-model="scoreForm.student_id"
                      placeholder="搜索并选择学生"
                      filterable
                      remote
                      :remote-method="searchStudents"
                      :loading="scoreFormStudentSearching"
                      style="width: 100%"
                    >
                      <el-option
                        v-for="s in scoreFormStudentList"
                        :key="s.id"
                        :label="`${s.name} (${s.student_no}) — ${s.class_name}`"
                        :value="s.id"
                      />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="评价指标">
                    <el-cascader
                      v-model="scoreForm.indicator_path"
                      :options="indicatorCascaderOptions"
                      :props="{ label: 'name', value: 'id', emitPath: false }"
                      placeholder="选择维度→具体指标"
                      style="width: 100%"
                      clearable
                      filterable
                    />
                  </el-form-item>

                  <el-form-item label="评分">
                    <el-input-number
                      v-model="scoreForm.score"
                      :min="0"
                      :max="20"
                      :precision="1"
                      style="width: 160px"
                    />
                    <span class="form-hint">(满分 {{ selectedIndicatorMax }})</span>
                  </el-form-item>

                  <el-form-item label="评分人类型">
                    <el-select v-model="scoreForm.scorer_type" style="width: 120px">
                      <el-option label="教师" value="teacher" />
                      <el-option label="自评" value="self" />
                      <el-option label="互评" value="peer" />
                      <el-option label="家长" value="parent" />
                      <el-option label="德育处" value="ms_admin" />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="评语">
                    <el-input
                      v-model="scoreForm.comment"
                      type="textarea"
                      :rows="2"
                      placeholder="可选，填写评分理由"
                    />
                  </el-form-item>

                  <el-form-item>
                    <el-button type="primary" :loading="scoreSaving" @click="submitScore">
                      <el-icon><Check /></el-icon> 提交评分
                    </el-button>
                    <el-button @click="resetScoreForm">重置</el-button>
                  </el-form-item>
                </el-form>
              </el-card>

              <!-- 评分规则概要 -->
              <el-card shadow="never" class="mt-3" v-if="rulesData">
                <template #header>
                  <span class="card-title-text">
                    <el-icon><Setting /></el-icon> 评分规则
                  </span>
                </template>
                <div class="rules-grid">
                  <div class="rule-item">
                    <span class="rule-label">基准分</span>
                    <span class="rule-value">{{ rulesData.base_score }}</span>
                  </div>
                  <div class="rule-item">
                    <span class="rule-label">五维权重</span>
                    <span class="rule-value">
                      德{{ (rulesData.weight_moral * 100).toFixed(0) }}%
                      学{{ (rulesData.weight_academic * 100).toFixed(0) }}%
                      身{{ (rulesData.weight_health * 100).toFixed(0) }}%
                      艺{{ (rulesData.weight_art * 100).toFixed(0) }}%
                      社{{ (rulesData.weight_social * 100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="rule-item">
                    <span class="rule-label">处分桥接</span>
                    <el-tag :type="rulesData.discipline_bridge_enabled ? 'success' : 'info'" size="small">
                      {{ rulesData.discipline_bridge_enabled ? '已启用' : '未启用' }}
                    </el-tag>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ── Tab 4: 流水审计 ───────────────────── -->
      <el-tab-pane label="流水审计" name="audit">
        <div class="tab-inner">
          <el-card shadow="never">
            <template #header>
              <div class="card-header-row">
                <span class="card-title-text">
                  <el-icon><Document /></el-icon> 评分流水审计
                </span>
                <div class="header-actions">
                  <el-select
                    v-model="auditStudentId"
                    placeholder="选择学生查看流水"
                    filterable
                    size="small"
                    style="width: 220px"
                    @change="loadScoreLogs"
                  >
                    <el-option
                      v-for="s in allStudents"
                      :key="s.id"
                      :label="`${s.name} (${s.student_no})`"
                      :value="s.id"
                    />
                  </el-select>
                </div>
              </div>
            </template>

            <el-table
              :data="auditLogs"
              v-loading="auditLoading"
              size="small"
              stripe
            >
              <el-table-column prop="created_at" label="时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="维度" width="90">
                <template #default="{ row }">
                  <el-tag size="small">{{ dimensionLabel(row.dimension) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="变动" width="80" align="center">
                <template #default="{ row }">
                  <span
                    :style="{
                      color: row.change_amount > 0 ? '#10b981' : row.change_amount < 0 ? '#ef4444' : '#909399',
                      fontWeight: '600'
                    }"
                  >
                    {{ row.change_amount > 0 ? '+' : '' }}{{ row.change_amount }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="前值" width="70" align="center">
                <template #default="{ row }">{{ row.before_score?.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="后值" width="70" align="center">
                <template #default="{ row }">{{ row.after_score?.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column prop="reason" label="原因" min-width="150" show-overflow-tooltip />
              <el-table-column label="来源" width="80">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain">
                    {{ row.source_type || '—' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="分类标签" width="100">
                <template #default="{ row }">
                  <el-tag
                    v-if="row.policy_tag"
                    size="small"
                    :type="policyTagType(row.policy_tag)"
                  >
                    {{ policyTagLabel(row.policy_tag) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="creator_name" label="操作人" width="90" />
            </el-table>

            <div class="audit-pagination">
              <el-pagination
                v-model:current-page="auditPage"
                :total="auditTotal"
                :page-size="50"
                layout="total, prev, pager, next"
                @current-change="loadScoreLogs"
                small
              />
            </div>

            <el-empty
              v-if="!auditStudentId && auditLogs.length === 0"
              description="请选择一名学生查看评分流水"
              :image-size="60"
            />
          </el-card>
        </div>
      </el-tab-pane>

      <!-- ── Tab 5: 期末评价 ───────────────────── -->
      <el-tab-pane label="期末评价" name="final">
        <div class="tab-inner">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <div class="card-header-row">
                    <span class="card-title-text">
                      <el-icon><Medal /></el-icon> 期末综合评价
                    </span>
                    <el-select
                      v-model="finalEvalStudentId"
                      placeholder="选择学生"
                      filterable
                      size="small"
                      style="width: 200px"
                      @change="loadFinalEvaluation"
                    >
                      <el-option
                        v-for="s in allStudents"
                        :key="s.id"
                        :label="`${s.name} (${s.student_no})`"
                        :value="s.id"
                      />
                    </el-select>
                  </div>
                </template>

                <div v-if="finalEvalData" v-loading="finalEvalLoading">
                  <!-- 最终等级 -->
                  <div class="final-grade-banner" :style="{ background: gradeBannerColor(finalEvalData.final_grade) }">
                    <div class="grade-letter">{{ finalEvalData.final_grade }}</div>
                    <div class="grade-text">{{ finalEvalData.grade_label }}</div>
                  </div>

                  <!-- 一票否决 -->
                  <el-alert
                    v-if="finalEvalData.veto.is_veto"
                    type="error"
                    :title="`一票否决：${finalEvalData.veto.reason || '处分熔断期'}`"
                    :closable="false"
                    show-icon
                    class="veto-alert"
                  />

                  <!-- 处分扣分详情 -->
                  <div v-if="finalEvalData.discipline_penalty.length > 0" class="section-header mt-4">
                    <el-icon><Warning /></el-icon> 处分扣分明细
                  </div>
                  <div
                    v-for="penalty in finalEvalData.discipline_penalty"
                    :key="penalty.sanction_id"
                    class="penalty-item"
                  >
                    <el-tag type="danger" size="small">{{ penalty.level }}</el-tag>
                    <span class="penalty-detail">扣除 {{ penalty.deduction }} 分</span>
                    <span class="penalty-date">{{ penalty.issued_date }}</span>
                  </div>

                  <!-- 已撤销处分 -->
                  <div v-if="finalEvalData.revoked_sanctions.length > 0" class="section-header mt-4">
                    <el-icon><CircleCheck /></el-icon> 已撤销处分
                  </div>
                  <div
                    v-for="rs in finalEvalData.revoked_sanctions"
                    :key="rs.sanction_id"
                    class="revoked-item"
                  >
                    <el-tag type="success" size="small">{{ rs.level }}</el-tag>
                    <span class="penalty-date">撤销日期: {{ rs.revoked_date }}</span>
                  </div>

                  <!-- 调整前后对比 -->
                  <div class="section-header mt-4">
                    <el-icon><DataAnalysis /></el-icon> 五维调整对比
                  </div>
                  <div class="compare-grid">
                    <div v-for="dim in dimensions" :key="dim.key" class="compare-item">
                      <span class="compare-label">{{ dim.label }}</span>
                      <div class="compare-values">
                        <span class="compare-base">{{ (finalEvalData.base_scores[dim.key] || 0).toFixed(1) }}</span>
                        <el-icon><ArrowRight /></el-icon>
                        <span
                          class="compare-adjusted"
                          :style="{
                            color: (finalEvalData.adjusted_scores[dim.key] || 0) < (finalEvalData.base_scores[dim.key] || 0)
                              ? '#ef4444' : '#10b981'
                          }"
                        >
                          {{ (finalEvalData.adjusted_scores[dim.key] || 0).toFixed(1) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <el-empty
                  v-if="!finalEvalData && !finalEvalLoading"
                  description="请选择一名学生查看期末综合评价"
                  :image-size="60"
                />
              </el-card>
            </el-col>

            <!-- 一票否决快查 -->
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <span class="card-title-text">
                    <el-icon><CloseBold /></el-icon> 一票否决快查
                  </span>
                </template>

                <div class="veto-check-area">
                  <el-select
                    v-model="vetoCheckStudentId"
                    placeholder="选择学生检查处分熔断"
                    filterable
                    size="default"
                    style="width: 100%"
                    @change="checkVeto"
                  >
                    <el-option
                      v-for="s in allStudents"
                      :key="s.id"
                      :label="`${s.name} (${s.student_no})`"
                      :value="s.id"
                    />
                  </el-select>

                  <div v-if="vetoResult" class="veto-result mt-3">
                    <el-alert
                      v-if="vetoResult.is_veto"
                      type="error"
                      :title="`学期总评熔断：${vetoResult.reason || 'D等'}`"
                      :closable="false"
                      show-icon
                    >
                      <template #default>
                        <div class="active-sanctions">
                          <div v-for="s in vetoResult.active_sanctions" :key="s.id" class="sanction-item">
                            <el-tag type="danger" size="small">{{ s.level }}</el-tag>
                            <span class="sanction-desc">{{ s.description || '—' }}</span>
                          </div>
                        </div>
                      </template>
                    </el-alert>
                    <el-alert
                      v-else
                      type="success"
                      title="无处分熔断，可正常评价"
                      :closable="false"
                      show-icon
                    />
                  </div>

                  <el-empty
                    v-if="!vetoResult"
                    description="选择学生以检查一票否决状态"
                    :image-size="60"
                    class="mt-3"
                  />
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══════════════════════════════════════ -->
    <!-- 指标编辑对话框                            -->
    <!-- ═══════════════════════════════════════ -->
    <el-dialog
      v-model="indicatorDialogVisible"
      :title="editingIndicator ? '编辑指标' : '新增指标'"
      width="500px"
    >
      <el-form :model="indicatorForm" label-width="100px">
        <el-form-item label="指标名称">
          <el-input v-model="indicatorForm.name" placeholder="如: 课堂纪律" />
        </el-form-item>
        <el-form-item label="所属维度">
          <el-select v-model="indicatorForm.dimension" style="width: 100%">
            <el-option
              v-for="dim in dimensions"
              :key="dim.key"
              :label="dim.label"
              :value="dim.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="indicatorForm.weight" :min="0" :max="10" :step="0.1" />
        </el-form-item>
        <el-form-item label="满分">
          <el-input-number v-model="indicatorForm.max_score" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="indicatorForm.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="indicatorDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="indicatorSaving" @click="saveIndicator">
          {{ editingIndicator ? '保存修改' : '创建指标' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Edit,
  Delete,
  Check,
  Search,
  User,
  Histogram,
  Trophy,
  List,
  EditPen,
  Setting,
  Document,
  Medal,
  Warning,
  CircleCheck,
  DataAnalysis,
  ArrowRight,
  CloseBold,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { useUserStore } from '@/store/user'
import { getClasses, getGrades, getStudents } from '@/api/classes'
import {
  listIndicators,
  createIndicator,
  updateIndicator,
  toggleIndicator,
  deleteIndicator,
  getRules,
  recordScore,
  getStudentScores,
  getClassRanking,
  getScoreLogs,
  getFinalEvaluation,
  checkDisciplineVeto,
  dimensionLabel,
  dimensionColor,
  gradeTagType,
  gradeLabel,
  DIMENSION_LABELS,
  DIMENSION_COLORS,
  getDemoIndicators,
  getDemoRules,
  getDemoStudentScores,
  getDemoClassRanking,
  getDemoScoreLogs,
  getDemoFinalEvaluation,
  type EvalDimension,
  type IndicatorGroupedOut,
  type IndicatorItem,
  type IndicatorCreate,
  type IndicatorUpdate,
  type StudentScoreOut,
  type ClassRankingOut,
  type ScoreLogListOut,
  type ScoreLogItem,
  type FinalEvaluationOut,
  type DisciplineVetoOut,
  type RuleOut,
} from '@/api/evaluation'

// --- 常量 ---
const dimensions = [
  { key: 'moral' as EvalDimension, label: '道德品质', color: '#ef4444' },
  { key: 'academic' as EvalDimension, label: '学业水平', color: '#3b82f6' },
  { key: 'health' as EvalDimension, label: '身心健康', color: '#10b981' },
  { key: 'art' as EvalDimension, label: '艺术素养', color: '#f59e0b' },
  { key: 'social' as EvalDimension, label: '社会实践', color: '#8b5cf6' },
]

// --- Store & State ---
const userStore = useUserStore()
const isAdmin = computed(() => userStore.currentRole === 'MS_ADMIN')
const semester = '2025-2026-2'

const activeTab = ref('portrait')

// 统计指标总数
const indicatorCount = computed(() => {
  let total = 0
  for (const g of indicatorGroups.value) {
    for (const item of g.items) {
      total += 1 + (item.children?.length || 0)
    }
  }
  return total
})

// ── Tab 1: 学生画像 ──────────────────────────
const studentSearchKeyword = ref('')
const selectedClassId = ref<number | null>(null)
const selectedStudent = ref<any>(null)
const currentScores = ref<StudentScoreOut | null>(null)
const studentsLoading = ref(false)
const scoresLoading = ref(false)
const allStudents = ref<any[]>([])
const classOptions = ref<{ id: number; name: string; grade_id?: number }[]>([])
const gradeOptions = ref<{ id: number; name: string }[]>([])
const selectedGradeId = ref<number | null>(null)

// filtered students for tab 1
const filteredClassOptions = computed(() => {
  if (!selectedGradeId.value) return classOptions.value
  return classOptions.value.filter((c: any) => c.grade_id === selectedGradeId.value)
})

const filteredStudents = computed(() => {
  let list = allStudents.value
  if (studentSearchKeyword.value) {
    const kw = studentSearchKeyword.value.toLowerCase()
    list = list.filter(
      (s) =>
        s.name?.toLowerCase().includes(kw) ||
        s.student_no?.toLowerCase().includes(kw),
    )
  }
  return list
})

// ECharts 实例
const radarChartRef = ref<HTMLDivElement | null>(null)
let radarChartInst: ReturnType<typeof echarts.init> | null = null

// ── Tab 2: 班级排名 ──────────────────────────
const rankingClassId = ref<number | null>(null)
const rankingGradeId = ref<number | null>(null)
const rankingFilteredClasses = computed(() => {
  if (!rankingGradeId.value) return classOptions.value
  return classOptions.value.filter((c: any) => c.grade_id === rankingGradeId.value)
})
const classRanking = ref<ClassRankingOut | null>(null)
const rankingLoading = ref(false)

// ── Tab 3: 评分管理 ──────────────────────────
const indicatorGroups = ref<IndicatorGroupedOut[]>([])
const indicatorsLoading = ref(false)
const rulesData = ref<RuleOut | null>(null)
const indicatorDialogVisible = ref(false)
const editingIndicator = ref<IndicatorItem | null>(null)
const indicatorSaving = ref(false)
const indicatorForm = ref<IndicatorCreate>({
  name: '',
  dimension: 'moral',
  weight: 1,
  max_score: 10,
  sort_order: 0,
})

// 录分表单
const scoreForm = ref({
  student_id: null as number | null,
  indicator_path: null as number | null,
  score: 10,
  scorer_type: 'teacher' as string,
  comment: '',
})
const scoreFormStudentSearching = ref(false)
const scoreFormStudentList = ref<any[]>([])
const scoreSaving = ref(false)

// 级联选择器选项
const indicatorCascaderOptions = computed(() => {
  return indicatorGroups.value.map((g) => ({
    name: g.dimension_label,
    id: `dim_${g.dimension}`,
    children: g.items.flatMap((item) => [
      { name: item.name, id: item.id },
      ...(item.children || []).map((child) => ({
        name: `  ${child.name}`,
        id: child.id,
      })),
    ]),
  }))
})

const selectedIndicatorMax = computed(() => {
  const id = scoreForm.value.indicator_path
  if (!id) return '—'
  for (const g of indicatorGroups.value) {
    for (const item of g.items) {
      if (item.id === id) return item.max_score
      if (item.children) {
        const child = item.children.find((c) => c.id === id)
        if (child) return child.max_score
      }
    }
  }
  return '—'
})

// ── Tab 4: 流水审计 ──────────────────────────
const auditStudentId = ref<number | null>(null)
const auditLogs = ref<ScoreLogItem[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)

// ── Tab 5: 期末评价 ──────────────────────────
const finalEvalStudentId = ref<number | null>(null)
const finalEvalData = ref<FinalEvaluationOut | null>(null)
const finalEvalLoading = ref(false)
const vetoCheckStudentId = ref<number | null>(null)
const vetoResult = ref<DisciplineVetoOut | null>(null)

// ═══════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════

function scoreColor(v: number): string {
  if (v >= 90) return '#10b981'
  if (v >= 75) return '#3b82f6'
  if (v >= 60) return '#f59e0b'
  return '#ef4444'
}

function getDimScore(scores: StudentScoreOut, dim: EvalDimension): number {
  const map: Record<string, number> = {
    moral: scores.moral_score,
    academic: scores.academic_score,
    health: scores.health_score,
    art: scores.art_score,
    social: scores.social_score,
  }
  return map[dim] ?? 0
}

function getDimPercent(scores: StudentScoreOut, dim: EvalDimension): number {
  return Math.min(100, Math.max(0, (getDimScore(scores, dim) / 100) * 100))
}

function formatDateTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function rankingRowClass({ row }: { row: any }) {
  if (row.rank <= 3) return 'top-rank'
  return ''
}

function rankTagType(rank: number): 'danger' | 'warning' | 'info' {
  if (rank === 1) return 'danger'
  if (rank === 2) return 'warning'
  return 'info'
}

function gradeBannerColor(grade: string): string {
  const map: Record<string, string> = {
    A: 'linear-gradient(135deg, #10b981, #059669)',
    B: 'linear-gradient(135deg, #3b82f6, #2563eb)',
    C: 'linear-gradient(135deg, #f59e0b, #d97706)',
    D: 'linear-gradient(135deg, #ef4444, #dc2626)',
  }
  return map[grade] || 'linear-gradient(135deg, #6b7280, #4b5563)'
}

function policyTagType(tag: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    repairable: 'warning',
    non_repairable: 'danger',
    recovered: 'success',
    permanent: 'info',
  }
  return map[tag] || 'info'
}

function policyTagLabel(tag: string): string {
  const map: Record<string, string> = {
    repairable: '可回血',
    non_repairable: '不可回血',
    recovered: '已恢复',
    permanent: '永久扣除',
  }
  return map[tag] || tag
}

// ═══════════════════════════════════════════════
// Tab 1: 学生画像
// ═══════════════════════════════════════════════

async function onGradeChange() {
  selectedClassId.value = null
  selectedStudent.value = null
  if (selectedGradeId.value) {
    const firstClass = filteredClassOptions.value[0]
    if (firstClass) {
      selectedClassId.value = firstClass.id
      loadClassStudents()
    }
  } else {
    allStudents.value = []
  }
}

async function onRankingGradeChange() {
  rankingClassId.value = null
  classRanking.value = null
  if (rankingGradeId.value) {
    const firstClass = rankingFilteredClasses.value[0]
    if (firstClass) {
      rankingClassId.value = firstClass.id
      loadClassRanking()
    }
  }
}

async function loadClassStudents() {
  studentsLoading.value = true
  try {
    if (selectedClassId.value) {
      // 先尝试评价模块的班级排名（有分数数据更丰富）
      const ranking = await getClassRanking(selectedClassId.value)
      if (ranking.ranking && ranking.ranking.length > 0) {
        const selectedClass = classOptions.value.find((c: any) => c.id === selectedClassId.value)
        const className = selectedClass?.name || `班级#${selectedClassId.value}`
        allStudents.value = ranking.ranking.map((r) => ({
          id: r.student_id,
          name: r.student_name,
          student_no: r.student_no,
          class_name: className,
          class_id: selectedClassId.value,
          grade_id: selectedGradeId.value || selectedClass?.grade_id,
          total_score: r.total_score,
        }))
      } else {
        // fallback: 班级无评价数据时，用核心学生API获取名单
        const res: any = await getStudents({ class_id: selectedClassId.value, page: 1, page_size: 200 })
        const list = res?.items ?? (Array.isArray(res) ? res : [])
        allStudents.value = list.map((s: any) => ({
          id: s.id,
          name: s.name,
          student_no: s.student_no || s.student_number,
          class_name: s.class_name || `班级#${s.class_id}`,
          class_id: s.class_id || selectedClassId.value,
          grade_id: s.grade_id || selectedGradeId.value,
          total_score: 0,
        }))
      }
    } else {
      allStudents.value = []
    }
  } catch {
    // 评价API异常时，fallback到核心学生API
    try {
      if (selectedClassId.value) {
        const res: any = await getStudents({ class_id: selectedClassId.value, page: 1, page_size: 200 })
        const list = res?.items ?? (Array.isArray(res) ? res : [])
        allStudents.value = list.map((s: any) => ({
          id: s.id,
          name: s.name,
          student_no: s.student_no || s.student_number,
          class_name: s.class_name || `班级#${s.class_id}`,
          class_id: s.class_id || selectedClassId.value,
          grade_id: s.grade_id || selectedGradeId.value,
          total_score: 0,
        }))
      } else {
        allStudents.value = []
      }
    } catch {
      allStudents.value = []
    }
  } finally {
    studentsLoading.value = false
  }
}

function selectStudent(student: any) {
  selectedStudent.value = student
  loadStudentScores()
}

async function loadStudentScores() {
  if (!selectedStudent.value) return
  scoresLoading.value = true
  try {
    currentScores.value = await getStudentScores(selectedStudent.value.id, semester)
    await nextTick()
    renderRadarChart()
  } catch {
    currentScores.value = getDemoStudentScores(selectedStudent.value.id)
    await nextTick()
    renderRadarChart()
  } finally {
    scoresLoading.value = false
  }
}

function renderRadarChart() {
  if (!radarChartRef.value || !currentScores.value) return
  if (!radarChartInst) {
    radarChartInst = echarts.init(radarChartRef.value)
  }

  const s = currentScores.value
  const option: any = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const dim = params.name
        const val = params.value
        return `<div style="font-weight:600">${selectedStudent.value?.name}</div><div>${dim}: ${val?.toFixed(1)}</div>`
      },
    },
    radar: {
      indicator: dimensions.map((d) => ({
        name: d.label,
        max: 100,
      })),
      center: ['50%', '52%'],
      radius: '70%',
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      splitLine: { lineStyle: { color: '#e4e7ed' } },
      axisName: { color: '#606266', fontSize: 12 },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [
              s.moral_score,
              s.academic_score,
              s.health_score,
              s.art_score,
              s.social_score,
            ],
            name: selectedStudent.value?.name || '学生',
            areaStyle: { color: 'rgba(64, 158, 255, 0.25)' },
            lineStyle: { color: '#409eff', width: 2 },
            itemStyle: { color: '#409eff' },
          },
        ],
      },
    ],
  }
  radarChartInst.setOption(option, true)
}

// ═══════════════════════════════════════════════
// Tab 2: 班级排名
// ═══════════════════════════════════════════════

async function loadClassRanking() {
  if (!rankingClassId.value) return
  rankingLoading.value = true
  try {
    classRanking.value = await getClassRanking(rankingClassId.value)
  } catch {
    classRanking.value = getDemoClassRanking(rankingClassId.value)
  } finally {
    rankingLoading.value = false
  }
}

// ═══════════════════════════════════════════════
// Tab 3: 指标管理 + 录分
// ═══════════════════════════════════════════════

async function loadIndicators() {
  indicatorsLoading.value = true
  try {
    indicatorGroups.value = await listIndicators()
  } catch {
    indicatorGroups.value = getDemoIndicators()
  } finally {
    indicatorsLoading.value = false
  }
}

async function loadRules() {
  try {
    rulesData.value = await getRules()
  } catch {
    rulesData.value = getDemoRules()
  }
}

function showIndicatorDialog(item: IndicatorItem | null) {
  editingIndicator.value = item
  if (item) {
    indicatorForm.value = {
      name: item.name,
      dimension: 'moral', // fallback
      weight: item.weight,
      max_score: item.max_score,
      sort_order: item.sort_order,
    }
  } else {
    indicatorForm.value = {
      name: '',
      dimension: 'moral',
      weight: 1,
      max_score: 10,
      sort_order: 0,
    }
  }
  indicatorDialogVisible.value = true
}

async function saveIndicator() {
  indicatorSaving.value = true
  try {
    if (editingIndicator.value) {
      await updateIndicator(editingIndicator.value.id, indicatorForm.value)
      ElMessage.success('指标已更新')
    } else {
      await createIndicator(indicatorForm.value)
      ElMessage.success('指标已创建')
    }
    indicatorDialogVisible.value = false
    loadIndicators()
  } catch {
    ElMessage.error('操作失败，请重试')
  } finally {
    indicatorSaving.value = false
  }
}

async function handleToggleIndicator(item: IndicatorItem) {
  try {
    await toggleIndicator(item.id)
    ElMessage.success(`指标「${item.name}」已${item.enabled ? '启用' : '禁用'}`)
  } catch {
    // revert toggle
    item.enabled = !item.enabled
    ElMessage.error('操作失败')
  }
}

async function handleDeleteIndicator(item: IndicatorItem) {
  try {
    await ElMessageBox.confirm(`确定要删除指标「${item.name}」吗？`, '确认删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await deleteIndicator(item.id)
    ElMessage.success('指标已删除')
    loadIndicators()
  } catch {
    // user cancelled or error
  }
}

async function searchStudents(query: string) {
  if (!query || query.length < 1) {
    scoreFormStudentList.value = []
    return
  }
  scoreFormStudentSearching.value = true
  try {
    // 使用已有的学生列表过滤
    scoreFormStudentList.value = allStudents.value.filter(
      (s) =>
        s.name?.toLowerCase().includes(query.toLowerCase()) ||
        s.student_no?.toLowerCase().includes(query.toLowerCase()),
    )
    if (scoreFormStudentList.value.length === 0) {
      // ensure student list is loaded
      await loadAllStudents()
      scoreFormStudentList.value = allStudents.value.filter(
        (s) =>
          s.name?.toLowerCase().includes(query.toLowerCase()) ||
          s.student_no?.toLowerCase().includes(query.toLowerCase()),
      )
    }
  } finally {
    scoreFormStudentSearching.value = false
  }
}

async function submitScore() {
  if (!scoreForm.value.student_id || !scoreForm.value.indicator_path) {
    ElMessage.warning('请选择学生和评价指标')
    return
  }
  scoreSaving.value = true
  try {
    await recordScore({
      student_id: scoreForm.value.student_id,
      class_id: selectedStudent.value?.class_id || selectedClassId.value,
      grade_id: selectedStudent.value?.grade_id || selectedGradeId.value,
      indicator_id: scoreForm.value.indicator_path,
      score: scoreForm.value.score,
      scorer_type: scoreForm.value.scorer_type as any,
      semester,
      comment: scoreForm.value.comment || undefined,
    })
    ElMessage.success('评分已提交')
    resetScoreForm()
    // 如果当前选中的学生就是评分的对象，刷新其数据
    if (selectedStudent.value?.id === scoreForm.value.student_id) {
      loadStudentScores()
    }
  } catch {
    ElMessage.error('评分提交失败')
  } finally {
    scoreSaving.value = false
  }
}

function resetScoreForm() {
  scoreForm.value = {
    student_id: null,
    indicator_path: null,
    score: 10,
    scorer_type: 'teacher',
    comment: '',
  }
}

async function loadAllStudents() {
  if (allStudents.value.length > 0) return
  studentsLoading.value = true
  try {
    const results: any[] = []
    for (const c of classOptions.value) {
      try {
        const ranking = await getClassRanking(c.id)
        if (ranking.ranking && ranking.ranking.length > 0) {
          results.push(
            ...ranking.ranking.map((r) => ({
              id: r.student_id,
              name: r.student_name,
              student_no: r.student_no,
              class_name: c.name,
              class_id: c.id,
              grade_id: c.grade_id,
              total_score: r.total_score,
            })),
          )
        } else {
          // 班级无评价数据，fallback到核心学生API
          try {
            const res: any = await getStudents({ class_id: c.id, page: 1, page_size: 200 })
            const list = res?.items ?? (Array.isArray(res) ? res : [])
            results.push(
              ...list.map((s: any) => ({
                id: s.id,
                name: s.name,
                student_no: s.student_no || s.student_number,
                class_name: s.class_name || c.name,
                class_id: s.class_id || c.id,
                grade_id: s.grade_id || c.grade_id,
                total_score: 0,
              })),
            )
          } catch {
            // skip failed class fallback
          }
        }
      } catch {
        // skip failed class
      }
    }
    if (results.length > 0) {
      allStudents.value = results
    } else {
      // 全部失败时，直接用核心API
      const res: any = await getStudents({ page: 1, page_size: 500 })
      const list = res?.items ?? (Array.isArray(res) ? res : [])
      allStudents.value = list.map((s: any) => ({
        id: s.id,
        name: s.name,
        student_no: s.student_no || s.student_number,
        class_name: s.class_name || `班级#${s.class_id}`,
        class_id: s.class_id,
        grade_id: s.grade_id,
        total_score: 0,
      }))
    }
  } catch {
    allStudents.value = []
  } finally {
    studentsLoading.value = false
  }
}

// ═══════════════════════════════════════════════
// Tab 4: 流水审计
// ═══════════════════════════════════════════════

async function loadScoreLogs() {
  if (!auditStudentId.value) return
  auditLoading.value = true
  try {
    const res = await getScoreLogs(auditStudentId.value, auditPage.value)
    auditLogs.value = res.items
    auditTotal.value = res.total
  } catch {
    const demo = getDemoScoreLogs(auditStudentId.value)
    auditLogs.value = demo.items
    auditTotal.value = demo.total
  } finally {
    auditLoading.value = false
  }
}

// ═══════════════════════════════════════════════
// Tab 5: 期末评价
// ═══════════════════════════════════════════════

async function loadFinalEvaluation() {
  if (!finalEvalStudentId.value) return
  finalEvalLoading.value = true
  try {
    finalEvalData.value = await getFinalEvaluation(finalEvalStudentId.value, semester)
  } catch {
    finalEvalData.value = getDemoFinalEvaluation(finalEvalStudentId.value)
  } finally {
    finalEvalLoading.value = false
  }
}

async function checkVeto() {
  if (!vetoCheckStudentId.value) return
  try {
    vetoResult.value = await checkDisciplineVeto(vetoCheckStudentId.value, semester)
  } catch {
    vetoResult.value = {
      student_id: vetoCheckStudentId.value,
      is_veto: false,
      reason: null,
      active_sanctions: [],
      semester,
    }
  }
}

// ═══════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════

onMounted(async () => {
  // 加载基础数据
  await Promise.all([loadIndicators(), loadRules()])

  // 加载年级和班级列表 (使用真实API)
  try {
    const gradesRes: any = await getGrades()
    const gradesList = gradesRes?.items ?? (Array.isArray(gradesRes) ? gradesRes : [])
    gradeOptions.value = gradesList.map((g: any) => ({ id: g.id, name: g.name }))

    const classesRes: any = await getClasses()
    const classesList = classesRes?.items ?? (Array.isArray(classesRes) ? classesRes : [])
    classOptions.value = classesList.map((c: any) => ({
      id: c.id,
      name: c.name,
      grade_id: c.grade_id,
    }))
  } catch {
    // Fallback to demo data
    classOptions.value = Array.from({ length: 8 }, (_, i) => ({
      id: i + 1,
      name: `七(${i + 1})班`,
      grade_id: 1,
    }))
    gradeOptions.value = [{ id: 1, name: '七年级' }]
  }

  // 默认选择第一个年级和班级
  if (gradeOptions.value.length > 0) {
    selectedGradeId.value = gradeOptions.value[0].id
    rankingGradeId.value = gradeOptions.value[0].id
  }
  if (classOptions.value.length > 0) {
    const firstClassOfClass = filteredClassOptions.value[0]
    if (firstClassOfClass) {
      selectedClassId.value = firstClassOfClass.id
    }
    const firstRankingClass = rankingFilteredClasses.value[0]
    if (firstRankingClass) {
      rankingClassId.value = firstRankingClass.id
    }
    loadClassStudents()
    loadClassRanking()
  }

  // 预加载所有学生
  await loadAllStudents()
})

onBeforeUnmount(() => {
  if (radarChartInst) {
    radarChartInst.dispose()
    radarChartInst = null
  }
})
</script>

<style scoped>
.evaluation-center {
  height: 100%;
  display: flex;
  flex-direction: column;
}

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
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-subtitle {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
  display: block;
}

.eval-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.eval-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.tab-inner {
  min-height: 400px;
}

/* ── Student Selector Card ── */
.student-selector-card {
  height: calc(100vh - 260px);
  display: flex;
  flex-direction: column;
}

.student-selector-card :deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.mb-3 {
  margin-bottom: 12px;
}

.student-list {
  flex: 1;
  overflow-y: auto;
}

.student-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.student-item:hover {
  background: #f5f7fa;
}

.student-item.active {
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
}

.stu-avatar {
  background: #409eff;
  color: #fff;
  font-weight: 600;
  flex-shrink: 0;
}

.stu-info {
  flex: 1;
  min-width: 0;
}

.stu-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.stu-detail {
  display: block;
  font-size: 12px;
  color: #909399;
}

.stu-score {
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.stu-score.no-data {
  color: #c0c4cc;
  font-weight: 400;
  font-size: 14px;
}

/* ── Portrait Card ── */
.portrait-card {
  height: calc(100vh - 260px);
  display: flex;
  flex-direction: column;
}

.portrait-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
}

.radar-chart-dom {
  width: 100%;
  height: 300px;
}

.chart-title-text {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  text-align: center;
}

.score-detail-list {
  padding: 4px 0;
}

.score-detail-item {
  margin-bottom: 12px;
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.dim-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dim-label {
  flex: 1;
  font-size: 13px;
  color: #606266;
}

.dim-value {
  font-size: 15px;
  font-weight: 700;
}

.total-score-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.total-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.total-value {
  font-size: 28px;
  font-weight: 800;
}

.total-baseline {
  font-size: 12px;
  color: #909399;
}

/* ── Common ── */
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.card-title-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.empty-placeholder {
  height: calc(100vh - 300px);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── Ranking ── */
.ranking-stats {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stat-num {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.ranking-table {
  margin-top: 8px;
}

.score-highlight {
  font-weight: 700;
  font-size: 15px;
}

/* ── Indicator Tree ── */
.indicator-tree-card {
  height: calc(100vh - 310px);
  overflow-y: auto;
}

.indicator-group {
  margin-bottom: 16px;
}

.group-header {
  padding: 6px 12px;
  border-left: 3px solid #409eff;
  background: #f5f7fa;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.indicator-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #f2f3f5;
}

.item-info {
  display: flex;
  flex-direction: column;
}

.item-name {
  font-size: 13px;
  color: #303133;
}

.item-name.disabled {
  color: #c0c4cc;
  text-decoration: line-through;
}

.item-meta {
  font-size: 11px;
  color: #909399;
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── Score Form ── */
.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.mt-3 {
  margin-top: 12px;
}

.rules-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.rule-label {
  color: #909399;
  min-width: 80px;
}

.rule-value {
  color: #303133;
  font-weight: 500;
}

/* ── Audit ── */
.audit-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: center;
}

/* ── Final Evaluation ── */
.final-grade-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  border-radius: 10px;
  color: #fff;
}

.grade-letter {
  font-size: 48px;
  font-weight: 800;
  line-height: 1;
}

.grade-text {
  font-size: 18px;
  font-weight: 500;
}

.veto-alert {
  margin-top: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.penalty-item,
.revoked-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: #606266;
}

.penalty-detail {
  font-weight: 500;
}

.penalty-date {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

.compare-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.compare-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f2f3f5;
}

.compare-label {
  font-size: 13px;
  color: #606266;
}

.compare-values {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.compare-base {
  color: #909399;
}

.compare-adjusted {
  font-weight: 700;
}

/* ── Veto Check ── */
.veto-check-area {
  min-height: 200px;
}

.veto-result {
  margin-bottom: 12px;
}

.active-sanctions {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sanction-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sanction-desc {
  font-size: 13px;
  color: #606266;
}

/* ── Misc ── */
:deep(.el-tabs__nav) {
  padding-left: 8px;
}

:deep(.el-table .top-rank) {
  background-color: #fdf6ec;
}
</style>
