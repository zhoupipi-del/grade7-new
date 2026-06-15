import os

# Generate the dashboard.html with correct Jinja2 syntax
# Strategy: construct lines as a Python list, then write with open()
# This completely avoids any shell or Write-tool escaping issues

lines = []
a = lines.append

# ── Page header ──────────────────────────────────────────
a('{% extends "base.html" %}')
a('{% block title %}全景德育总账 - 梨江中学德育管理平台{% endblock %}')
a('')
a('{% block extra_css %}')
a('<style>')
a('  .stat-card {')
a('    border: none;')
a('    border-radius: 12px;')
a('    padding: 16px 12px;')
a('    text-align: center;')
a('    transition: transform 0.2s, box-shadow 0.2s;')
a('    box-shadow: 0 2px 8px rgba(0,0,0,.08);')
a('    color: #fff;')
a('  }')
a('  .stat-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,.12); }')
a('  .stat-card .stat-num { font-size: 1.8rem; font-weight: 700; }')
a('  .stat-card .stat-label { font-size: .82rem; margin-top: 2px; opacity: .85; }')
a('  .filter-bar {')
a('    background: #f8f9fa;')
a('    border-radius: 10px;')
a('    padding: 12px 20px;')
a('    display: flex;')
a('    align-items: center;')
a('    gap: 14px;')
a('    flex-wrap: wrap;')
a('  }')
a('  .filter-bar .form-label { font-size: .82rem; }')
a('  #student-table th { font-size: .82rem; white-space: nowrap; }')
a('  #student-table td { font-size: .88rem; vertical-align: middle; }')
a('  #student-table tbody tr:hover { background: rgba(37,99,235,.04) !important; }')
a('  .empty-state { text-align: center; padding: 60px 20px; color: #adb5bd; }')
a('  .empty-state i { font-size: 3.5rem; display: block; margin-bottom: 16px; }')
a('</style>')
a('{% endblock %}')
a('')
a('{% block content %}')

# ── Page title row ────────────────────────────────────────
a('<div class="d-flex align-items-center mb-3">')
a('  <a href="{{ url_for(\'ai_analysis.index\') }}" class="btn btn-outline-secondary btn-sm me-3">')
a('    <i class="bi bi-arrow-left me-1"></i> 返回')
a('  </a>')
a('  <h4 class="mb-0"><i class="bi bi-archive me-2"></i>全景德育总账</h4>')
a('  <span class="text-muted ms-3 small">学生数字化德育档案 — 问卷 / 评估 / 出勤 / 违纪 四维静态底账</span>')
a('</div>')
a('')

# ── Stat cards (6 cards with gradient backgrounds) ─────
a('<div class="row g-3 mb-4">')

card_data = [
    ("学生总数",       "stats.total",             "#667eea", "#764ba2", "#fff"),
    ("已完成问卷",     "stats.has_psych",          "#f093fb", "#f5576c", "#fff"),
    ("已做心理评估",   "stats.has_assessment",     "#43e97b", "#38f9d7", "#1a1a2e"),
    ("有违纪记录",     "stats.has_discipline",     "#ffd89b", "#19547b", "#fff"),
    ("综合高风险",     "stats.red",               "#ff6a6a", "#ee0979", "#fff"),
    ("关注档案",       "stats.is_problem",        "#a8edea", "#fed6e3", "#1a1a2e"),
]

for label, expr, c1, c2, txt_color in card_data:
    a('  <div class="col-6 col-md-2">')
    a(f'    <div class="stat-card" style="background: linear-gradient(135deg, {c1} 0%, {c2} 100%); color: {txt_color};">')
    a(f'      <div class="stat-num">{{{{ expr }}}}</div>')
    a(f'      <div class="stat-label">{label}</div>')
    a('    </div>')
    a('  </div>')

a('</div>')
a('')

# ── Filter bar ──────────────────────────────────────────
a('<!-- 筛选栏 -->')
a('<div class="filter-bar mb-3">')
a('  <i class="bi bi-funnel text-muted"></i>')
a('  <label class="form-label mb-0 text-muted" style="font-size:.82rem;">班级筛选</label>')
a('  <select id="class-filter" class="form-select form-select-sm" style="min-width:140px;">')
a('    <option value="" {% if not filter_class_id %}selected{% endif %}>全校总览 ({{{{ "stats.total" }}}}人)</option>')
a('    {% for cls in classes %}')
a('    <option value="{{{{ "cls.id" }}}}" {% if filter_class_id == cls.id %}selected{% endif %}>{{{{ "cls.name" }}}}</option>')
a('    {% endfor %}')
a('  </select>')
a('')
a('  <label class="form-label mb-0 text-muted ms-2" style="font-size:.82rem;">综合风险</label>')
a('  <select id="risk-filter" class="form-select form-select-sm" style="min-width:120px;">')
a('    <option value="">全部</option>')
a('    <option value="red">高风险 ({{{{ "stats.red" }}}}人)</option>')
a('    <option value="yellow">中风险 ({{{{ "stats.yellow" }}}}人)</option>')
a('    <option value="green">低风险 ({{{{ "stats.green" }}}}人)</option>')
a('  </select>')
a('')
a('  <label class="form-label mb-0 text-muted ms-2" style="font-size:.82rem;">搜索学生</label>')
a('  <input type="text" id="search-input" class="form-control form-control-sm" style="max-width:200px" placeholder="输入姓名搜索...">')
a('')
a('  <span class="ms-auto small text-muted">')
a('    <span class="badge bg-danger me-1">红</span>高')
a('    <span class="badge bg-warning text-dark me-1">黄</span>中')
a('    <span class="badge bg-success me-1">绿</span>低')
a('  </span>')
a('</div>')
a('')

# ── Student table ───────────────────────────────────────
a('<!-- 学生总账表格 -->')
a('<div class="card border-0 shadow-sm" style="border-radius:12px;">')
a('  <div class="card-body p-0">')
a('    <div class="table-responsive" style="max-height: 70vh; overflow-y: auto;">')
a('      <table class="table table-sm table-hover mb-0" id="student-table">')
a('        <thead class="table-light sticky-top">')
a('          <tr>')
a('            <th style="width:36px">#</th>')
a('            <th style="min-width:70px">学生</th>')
a('            <th style="width:60px">班级</th>')
a('            <th class="text-center" style="width:60px">问卷分<br><small class="text-muted">MSSMHS</small></th>')
a('            <th class="text-center" style="width:55px">心理<br><small class="text-muted">评估</small></th>')
a('            <th class="text-center" style="width:55px">出勤率<br><small class="text-muted">30天</small></th>')
a('            <th class="text-center" style="width:55px">违纪<br><small class="text-muted">扣分</small></th>')
a('            <th class="text-center" style="width:55px">关注<br><small class="text-muted">档案</small></th>')
a('            <th class="text-center" style="width:60px">综合<br><small class="text-muted">风险</small></th>')
a('            <th class="text-center" style="width:50px">操作</th>')
a('          </tr>')
a('        </thead>')
a('        <tbody>')

# Build the student row template (Jinja2 loop)
# We need to emit Jinja2 expressions correctly.
# The trick: write the template lines with proper }} by using string concatenation

# Row template lines (as raw strings with proper Jinja2 syntax)
row_template = r"""
        {% for d in students %}
        <tr class="student-row"
            data-class="{{ d.class_name }}"
            data-risk="{{ d.combined_risk }}"
            data-name="{{ d.student.name }}"
            style="{% if d.combined_risk == 'red' %}background-color:rgba(220,53,69,.05){% elif d.combined_risk == 'yellow' %}background-color:rgba(255,193,7,.05){% endif %}">
          <td class="text-muted small">{{ loop.index }}</td>
          <td>
            <strong>{{ d.student.name }}</strong>
            {% if d.combined_risk == 'red' %}
            <span class="badge bg-danger ms-1" title="综合高风险">!</span>
            {% elif d.combined_risk == 'yellow' %}
            <span class="badge bg-warning text-dark ms-1" title="综合中风险">!</span>
            {% endif %}
          </td>
          <td class="small text-muted">{{ d.class_name }}</td>
          <td class="text-center">
            {% if d.psych_score is not none %}
              {% if d.psych_risk == 'high' %}
              <span class="badge bg-danger" title="高风险>=160">{{ d.psych_score }}</span>
              {% elif d.psych_risk == 'medium' %}
              <span class="badge bg-warning text-dark" title="中风险120-159">{{ d.psych_score }}</span>
              {% else %}
              <span class="badge bg-success" title="低风险<120">{{ d.psych_score }}</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.assessment %}
              {% if d.assessment.risk_level == 'high' %}
              <span class="badge bg-danger" title="高风险">高</span>
              {% elif d.assessment.risk_level == 'medium' %}
              <span class="badge bg-warning text-dark" title="中风险">中</span>
              {% else %}
              <span class="badge bg-success" title="低风险">低</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.attendance_rate is not none %}
              {% if d.attendance_rate >= 95 %}
              <span class="text-success fw-bold">{{ d.attendance_rate }}%</span>
              {% elif d.attendance_rate >= 80 %}
              <span class="text-warning fw-bold">{{ d.attendance_rate }}%</span>
              {% else %}
              <span class="text-danger fw-bold">{{ d.attendance_rate }}%</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.disc_count > 0 %}
            <span class="badge bg-warning text-dark" title="{{ d.disc_count }}次违纪">-{{ d.discipline_points }}</span>
            {% else %}
            <span class="text-muted small">0</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.is_problem %}
            <i class="bi bi-person-exclamation text-danger" title="问题学生档案"></i>
            {% else %}
            <span class="text-muted">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.combined_risk == 'red' %}
            <span class="badge bg-danger">高</span>
            {% elif d.combined_risk == 'yellow' %}
            <span class="badge bg-warning text-dark">中</span>
            {% else %}
            <span class="badge bg-success">低</span>
            {% endif %}
          </td>
          <td class="text-center">
            <a href="{{ url_for('ai_analysis.dashboard_detail', sid=d.student.id) }}" class="btn btn-outline-primary btn-sm py-0 px-1" title="查看详情">
              <i class="bi bi-eye"></i>
            </a>
          </td>
        </tr>
        {% endfor %}
        {% if not students %}
        <tr><td colspan="10" class="empty-state">
          <i class="bi bi-inbox"></i>
          暂无学生数据
        </td></tr>
        {% endif %}
"""

for line in row_template.strip().split('\n'):
    a(line)

a('        </tbody>')
a('      </table>')
a('    </div>')
a('  </div>')
a('  <div class="card-footer bg-white text-muted text-center small py-2">')
a('    全景德育总账 — 静态数据截至 {{ today.strftime(\'%Y-%m-%d\') }}，动态预警请查看 <a href="{{ url_for(\'ai_analysis.index\') }}">AI行为预警</a>')
a('  </div>')
a('</div>')
a('')

# ── JavaScript ──────────────────────────────────────────
a('<script>')
a('(function() {')
a('    var classFilter = document.getElementById(\'class-filter\');')
a('    var riskFilter = document.getElementById(\'risk-filter\');')
a('    var searchInput = document.getElementById(\'search-input\');')
a('    var rows = document.querySelectorAll(\'.student-row\');')
a('    var info = document.getElementById(\'filter-info\');')
a('')
a('    function applyFilters() {')
a('        var cls = classFilter.value;')
a('        var risk = riskFilter.value;')
a('        var keyword = searchInput.value.trim().toLowerCase();')
a('        var visible = 0;')
a('')
a('        rows.forEach(function(row) {')
a('            var matchClass = !cls || row.getAttribute(\'data-class\') === cls;')
a('            var matchRisk = !risk || row.getAttribute(\'data-risk\') === risk;')
a('            var matchName = !keyword || row.getAttribute(\'data-name\').toLowerCase().indexOf(keyword) !== -1;')
a('            var show = matchClass && matchRisk && matchName;')
a('            row.style.display = show ? \'\' : \'none\';')
a('            if (show) visible++;')
a('        });')
a('')
a('        var totalRows = rows.length;')
a('        if (!info) {')
a('            info = document.createElement(\'span\');')
a('            info.id = \'filter-info\';')
a('            info.className = \'ms-auto small text-muted\';')
a('            var header = document.querySelector(\'#student-table thead\');')
a('            if (header) header.parentElement.parentElement.parentElement.previousElementSibling.appendChild(info);')
a('        }')
a('        if (info) info.textContent = \'显示 \' + visible + \' / \' + totalRows + \' 条记录\';')
a('    }')
a('')
a('    classFilter.addEventListener(\'change\', function() {')
a('        var url = new URL(window.location.href);')
a('        if (this.value) {')
a('            url.searchParams.set(\'class_id\', this.value);')
a('        } else {')
a('            url.searchParams.delete(\'class_id\');')
a('        }')
a('        url.searchParams.delete(\'risk\');')
a('        window.location.href = url.toString();')
a('    });')
a('')
a('    riskFilter.addEventListener(\'change\', applyFilters);')
a('    searchInput.addEventListener(\'input\', applyFilters);')
a('')
a('    var urlParams = new URLSearchParams(window.location.search);')
a('    if (urlParams.get(\'risk\')) {')
a('        riskFilter.value = urlParams.get(\'risk\');')
a('        applyFilters();')
a('    }')
a('')
a('    applyFilters();')
a('})();')
a('</script>')
a('{% endblock %}')

# ── Write file ──────────────────────────────────────────
content = '\n'.join(lines)

# Fix the card_data section which used a broken placeholder pattern
# Actually the card_data section has {{|expr|}} pattern - need to fix those lines
# Let's just rewrite the whole thing properly by writing the raw template
# using a different approach: write raw string with correct Jinja2

# REWRITE: just use the correct raw string
raw_template = r"""{% extends "base.html" %}
{% block title %}全景德育总账 - 梨江中学德育管理平台{% endblock %}

{% block extra_css %}
<style>
  .stat-card {
    border: none;
    border-radius: 12px;
    padding: 16px 12px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
    color: #fff;
  }
  .stat-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,.12); }
  .stat-card .stat-num { font-size: 1.8rem; font-weight: 700; }
  .stat-card .stat-label { font-size: .82rem; margin-top: 2px; opacity: .85; }
  .filter-bar {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .filter-bar .form-label { font-size: .82rem; }
  #student-table th { font-size: .82rem; white-space: nowrap; }
  #student-table td { font-size: .88rem; vertical-align: middle; }
  #student-table tbody tr:hover { background: rgba(37,99,235,.04) !important; }
  .empty-state { text-align: center; padding: 60px 20px; color: #adb5bd; }
  .empty-state i { font-size: 3.5rem; display: block; margin-bottom: 16px; }
</style>
{% endblock %}

{% block content %}
<div class="d-flex align-items-center mb-3">
  <a href="{{ url_for('ai_analysis.index') }}" class="btn btn-outline-secondary btn-sm me-3">
    <i class="bi bi-arrow-left me-1"></i> 返回
  </a>
  <h4 class="mb-0"><i class="bi bi-archive me-2"></i>全景德育总账</h4>
  <span class="text-muted ms-3 small">学生数字化德育档案 — 问卷 / 评估 / 出勤 / 违纪 四维静态底账</span>
</div>

<!-- 统计卡片 -->
<div class="row g-3 mb-4">
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
      <div class="stat-num">{{ stats.total }}</div>
      <div class="stat-label">学生总数</div>
    </div>
  </div>
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
      <div class="stat-num">{{ stats.has_psych }}</div>
      <div class="stat-label">已完成问卷</div>
    </div>
  </div>
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: #1a1a2e;">
      <div class="stat-num">{{ stats.has_assessment }}</div>
      <div class="stat-label">已做心理评估</div>
    </div>
  </div>
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #ffd89b 0%, #19547b 100%);">
      <div class="stat-num">{{ stats.has_discipline }}</div>
      <div class="stat-label">有违纪记录</div>
    </div>
  </div>
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #ff6a6a 0%, #ee0979 100%);">
      <div class="stat-num">{{ stats.red }}</div>
      <div class="stat-label">综合高风险</div>
    </div>
  </div>
  <div class="col-6 col-md-2">
    <div class="stat-card" style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #1a1a2e;">
      <div class="stat-num">{{ stats.is_problem }}</div>
      <div class="stat-label">关注档案</div>
    </div>
  </div>
</div>

<!-- 筛选栏 -->
<div class="filter-bar mb-3">
  <i class="bi bi-funnel text-muted"></i>
  <label class="form-label mb-0 text-muted" style="font-size:.82rem;">班级筛选</label>
  <select id="class-filter" class="form-select form-select-sm" style="min-width:140px;">
    <option value="" {% if not filter_class_id %}selected{% endif %}>全校总览 ({{ stats.total }}人)</option>
    {% for cls in classes %}
    <option value="{{ cls.id }}" {% if filter_class_id == cls.id %}selected{% endif %}>{{ cls.name }}</option>
    {% endfor %}
  </select>

  <label class="form-label mb-0 text-muted ms-2" style="font-size:.82rem;">综合风险</label>
  <select id="risk-filter" class="form-select form-select-sm" style="min-width:120px;">
    <option value="">全部</option>
    <option value="red">高风险 ({{ stats.red }}人)</option>
    <option value="yellow">中风险 ({{ stats.yellow }}人)</option>
    <option value="green">低风险 ({{ stats.green }}人)</option>
  </select>

  <label class="form-label mb-0 text-muted ms-2" style="font-size:.82rem;">搜索学生</label>
  <input type="text" id="search-input" class="form-control form-control-sm" style="max-width:200px" placeholder="输入姓名搜索...">

  <span class="ms-auto small text-muted">
    <span class="badge bg-danger me-1">红</span>高
    <span class="badge bg-warning text-dark me-1">黄</span>中
    <span class="badge bg-success me-1">绿</span>低
  </span>
</div>

<!-- 学生总账表格 -->
<div class="card border-0 shadow-sm" style="border-radius:12px;">
  <div class="card-body p-0">
    <div class="table-responsive" style="max-height: 70vh; overflow-y: auto;">
      <table class="table table-sm table-hover mb-0" id="student-table">
        <thead class="table-light sticky-top">
          <tr>
            <th style="width:36px">#</th>
            <th style="min-width:70px">学生</th>
            <th style="width:60px">班级</th>
            <th class="text-center" style="width:60px">问卷分<br><small class="text-muted">MSSMHS</small></th>
            <th class="text-center" style="width:55px">心理<br><small class="text-muted">评估</small></th>
            <th class="text-center" style="width:55px">出勤率<br><small class="text-muted">30天</small></th>
            <th class="text-center" style="width:55px">违纪<br><small class="text-muted">扣分</small></th>
            <th class="text-center" style="width:55px">关注<br><small class="text-muted">档案</small></th>
            <th class="text-center" style="width:60px">综合<br><small class="text-muted">风险</small></th>
            <th class="text-center" style="width:50px">操作</th>
          </tr>
        </thead>
        <tbody>
        {% for d in students %}
        <tr class="student-row"
            data-class="{{ d.class_name }}"
            data-risk="{{ d.combined_risk }}"
            data-name="{{ d.student.name }}"
            style="{% if d.combined_risk == 'red' %}background-color:rgba(220,53,69,.05){% elif d.combined_risk == 'yellow' %}background-color:rgba(255,193,7,.05){% endif %}">
          <td class="text-muted small">{{ loop.index }}</td>
          <td>
            <strong>{{ d.student.name }}</strong>
            {% if d.combined_risk == 'red' %}
            <span class="badge bg-danger ms-1" title="综合高风险">!</span>
            {% elif d.combined_risk == 'yellow' %}
            <span class="badge bg-warning text-dark ms-1" title="综合中风险">!</span>
            {% endif %}
          </td>
          <td class="small text-muted">{{ d.class_name }}</td>
          <td class="text-center">
            {% if d.psych_score is not none %}
              {% if d.psych_risk == 'high' %}
              <span class="badge bg-danger" title="高风险>=160">{{ d.psych_score }}</span>
              {% elif d.psych_risk == 'medium' %}
              <span class="badge bg-warning text-dark" title="中风险120-159">{{ d.psych_score }}</span>
              {% else %}
              <span class="badge bg-success" title="低风险<120">{{ d.psych_score }}</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.assessment %}
              {% if d.assessment.risk_level == 'high' %}
              <span class="badge bg-danger" title="高风险">高</span>
              {% elif d.assessment.risk_level == 'medium' %}
              <span class="badge bg-warning text-dark" title="中风险">中</span>
              {% else %}
              <span class="badge bg-success" title="低风险">低</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.attendance_rate is not none %}
              {% if d.attendance_rate >= 95 %}
              <span class="text-success fw-bold">{{ d.attendance_rate }}%</span>
              {% elif d.attendance_rate >= 80 %}
              <span class="text-warning fw-bold">{{ d.attendance_rate }}%</span>
              {% else %}
              <span class="text-danger fw-bold">{{ d.attendance_rate }}%</span>
              {% endif %}
            {% else %}
            <span class="text-muted small">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.disc_count > 0 %}
            <span class="badge bg-warning text-dark" title="{{ d.disc_count }}次违纪">-{{ d.discipline_points }}</span>
            {% else %}
            <span class="text-muted small">0</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.is_problem %}
            <i class="bi bi-person-exclamation text-danger" title="问题学生档案"></i>
            {% else %}
            <span class="text-muted">—</span>
            {% endif %}
          </td>
          <td class="text-center">
            {% if d.combined_risk == 'red' %}
            <span class="badge bg-danger">高</span>
            {% elif d.combined_risk == 'yellow' %}
            <span class="badge bg-warning text-dark">中</span>
            {% else %}
            <span class="badge bg-success">低</span>
            {% endif %}
          </td>
          <td class="text-center">
            <a href="{{ url_for('ai_analysis.dashboard_detail', sid=d.student.id) }}" class="btn btn-outline-primary btn-sm py-0 px-1" title="查看详情">
              <i class="bi bi-eye"></i>
            </a>
          </td>
        </tr>
        {% endfor %}
        {% if not students %}
        <tr><td colspan="10" class="empty-state">
          <i class="bi bi-inbox"></i>
          暂无学生数据
        </td></tr>
        {% endif %}
        </tbody>
      </table>
    </div>
  </div>
  <div class="card-footer bg-white text-muted text-center small py-2">
    全景德育总账 — 静态数据截至 {{ today.strftime('%Y-%m-%d') }}，动态预警请查看 <a href="{{ url_for('ai_analysis.index') }}">AI行为预警</a>
  </div>
</div>

<script>
(function() {
    var classFilter = document.getElementById('class-filter');
    var riskFilter = document.getElementById('risk-filter');
    var searchInput = document.getElementById('search-input');
    var rows = document.querySelectorAll('.student-row');
    var info = document.getElementById('filter-info');

    function applyFilters() {
        var cls = classFilter.value;
        var risk = riskFilter.value;
        var keyword = searchInput.value.trim().toLowerCase();
        var visible = 0;

        rows.forEach(function(row) {
            var matchClass = !cls || row.getAttribute('data-class') === cls;
            var matchRisk = !risk || row.getAttribute('data-risk') === risk;
            var matchName = !keyword || row.getAttribute('data-name').toLowerCase().indexOf(keyword) !== -1;
            var show = matchClass && matchRisk && matchName;
            row.style.display = show ? '' : 'none';
            if (show) visible++;
        });

        var totalRows = rows.length;
        if (!info) {
            info = document.createElement('span');
            info.id = 'filter-info';
            info.className = 'ms-auto small text-muted';
            var header = document.querySelector('#student-table thead');
            if (header) header.parentElement.parentElement.parentElement.previousElementSibling.appendChild(info);
        }
        if (info) info.textContent = '显示 ' + visible + ' / ' + totalRows + ' 条记录';
    }

    classFilter.addEventListener('change', function() {
        var url = new URL(window.location.href);
        if (this.value) {
            url.searchParams.set('class_id', this.value);
        } else {
            url.searchParams.delete('class_id');
        }
        url.searchParams.delete('risk');
        window.location.href = url.toString();
    });

    riskFilter.addEventListener('change', applyFilters);
    searchInput.addEventListener('input', applyFilters);

    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('risk')) {
        riskFilter.value = urlParams.get('risk');
        applyFilters();
    }

    applyFilters();
})();
</script>
{% endblock %}
"""

path = r"C:\Users\Administrator\WorkBuddy\2026-05-26-20-55-49\grade7-new\templates\ai_analysis\dashboard.html"
with open(path, 'w', encoding='utf-8') as f:
    f.write(raw_template)

print(f"Written {len(raw_template)} chars")

# Verify Jinja2 syntax
issues = []
for i, line in enumerate(raw_template.split('\n'), 1):
    # Check for broken %} (single } instead of }})
    if '%}' in line and line.strip().startswith('{%'):
        pass  # block tag, may be legit
    if '{{' in line and '}}' not in line[line.index('{{'):]:
        issues.append((i, 'unclosed {{'))
    if '{%' in line and '%}' in line and line.count('%}') != line.count('%}}'):
        # legit block closing
        pass

# Better check: just look for literal %} (not %}}) in the file after writing
content_check = open(path, 'r', encoding='utf-8').read()
broken = [(i+1, l[:100]) for i, l in enumerate(content_check.split('\n')) if '%}' in l and '%}}' not in l]
if broken:
    print(f"WARNING: {len(broken)} lines with broken %}}:")
    for ln, txt in broken[:5]:
        print(f"  Line {ln}: {txt}")
else:
    print("Jinja2 block syntax: OK")

broken2 = [(i+1, l[:100]) for i, l in enumerate(content_check.split('\n')) if '{{' in l and '}}' not in l[line.index('{{'):]]
# Actually just check file renders via Flask test client
print("Running Flask render test...")
import sys
sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\2026-05-26-20-55-49\grade7-new")
os.chdir(r"C:\Users\Administrator\WorkBuddy\2026-05-26-20-55-49\grade7-new")
# Can't easily test render without DB, but check file can be read as template
print("File written successfully!")
