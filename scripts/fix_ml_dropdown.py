#!/usr/bin/env python3
"""在服务器上直接修复 ml_models 的4个预测页面
把"输入姓名搜索"改成"班级+学生下拉选择"
"""
import os, sys

TEMPLATE_DIR = "/opt/grade7-new/templates/ml_models"

def read_file(name):
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(name, content):
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Written: {path}")

# ============================================================
# 1. 修复 grade_prediction.html
# ============================================================
def fix_grade_prediction():
    content = read_file("grade_prediction.html")
    
    # 替换搜索面板（左侧卡片内容）
    old_search = '''            <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">学生姓名</label>
                        <input type="text" class="form-control" id="studentName" placeholder="输入学生姓名">
                    </div>
                    <button class="btn btn-primary w-100" onclick="predictGrades()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    new_search = '''            <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">选择班级</label>
                        <select class="form-select" id="classSelect" onchange="onClassChange()">
                            <option value="">-- 选择班级 --</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">选择学生</label>
                        <select class="form-select" id="studentSelect" disabled>
                            <option value="">-- 选择学生 --</option>
                        </select>
                    </div>
                    <button class="btn btn-primary w-100" onclick="predictGrades()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    if old_search in content:
        content = content.replace(old_search, new_search)
        print("  [grade] Search panel replaced")
    else:
        print("  [grade] WARNING: search panel pattern not found")
    
    # 替换 JS
    old_js = '''function predictGrades() {
    const name = document.getElementById('studentName').value.trim();
    if (!name) {
        alert('请输入学生姓名');
        return;
    }

    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';

    // 先搜索学生
    fetch(`/search/api?q=${encodeURIComponent(name)}&type=student`)
        .then(r => r.json())
        .then(data => {
            if (data.results && data.results.length > 0) {
                const student = data.results[0];
                document.getElementById('studentNameSpan').textContent = student.name;
                return fetch(`/ai-analysis/api/predict/grades/${student.id}`);
            } else {
                throw new Error('未找到该学生');
            }
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';

            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }

            document.getElementById('resultArea').style.display = 'block';
            const tbody = document.getElementById('resultsBody');
            tbody.innerHTML = '';

            (data.predictions || []).forEach(p => {
                const trendIcon = p.trend === 'rising' ? '📈' : (p.trend === 'declining' ? '📉' : '➡️');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${p.subject}</td>
                    <td>${p.historical ? p.historical.slice(-3).join(', ') + ', ...' : '-'}</td>
                    <td><strong>${p.predicted}</strong></td>
                    <td>${trendIcon} ${p.trend === 'rising' ? '上升' : (p.trend === 'declining' ? '下降' : '稳定')}</td>
                    <td>${Math.round(p.confidence * 100)}%</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}

// 回车搜索
document.getElementById('studentName').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') predictGrades();
});'''
    
    new_js = '''// 班级和学生数据
let studentMap = {};

function loadClasses() {
    fetch('/ml/api/classes')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('classSelect');
            sel.innerHTML = '<option value="">-- 选择班级 --</option>';
            (data.classes || []).forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                sel.appendChild(opt);
            });
        });
}

function onClassChange() {
    const cid = document.getElementById('classSelect').value;
    const stuSel = document.getElementById('studentSelect');
    stuSel.innerHTML = '<option value="">-- 选择学生 --</option>';
    stuSel.disabled = !cid;
    if (!cid) return;
    
    fetch(`/ml/api/students?class_id=${cid}`)
        .then(r => r.json())
        .then(data => {
            studentMap[cid] = data.students || [];
            data.students.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                stuSel.appendChild(opt);
            });
            stuSel.disabled = false;
        });
}

function predictGrades() {
    const sid = document.getElementById('studentSelect').value;
    if (!sid) { alert('请先选择学生'); return; }
    
    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';
    
    const studentName = document.getElementById('studentSelect').selectedOptions[0].text;
    document.getElementById('studentNameSpan').textContent = studentName;
    
    fetch(`/ai-analysis/api/predict/grades/${sid}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';

            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }

            document.getElementById('resultArea').style.display = 'block';
            const tbody = document.getElementById('resultsBody');
            tbody.innerHTML = '';

            (data.predictions || []).forEach(p => {
                const trendIcon = p.trend === 'rising' ? '📈' : (p.trend === 'declining' ? '📉' : '➡️');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${p.subject}</td>
                    <td>${p.historical ? p.historical.slice(-3).join(', ') + ', ...' : '-'}</td>
                    <td><strong>${p.predicted}</strong></td>
                    <td>${trendIcon} ${p.trend === 'rising' ? '上升' : (p.trend === 'declining' ? '下降' : '稳定')}</td>
                    <td>${Math.round(p.confidence * 100)}%</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadClasses();
});'''
    
    if old_js in content:
        content = content.replace(old_js, new_js)
        print("  [grade] JS replaced")
    else:
        print("  [grade] WARNING: JS pattern not found, trying partial...")
        # 尝试只替换函数定义
        if 'function predictGrades()' in content:
            print("  [grade] Found predictGrades function, but full pattern mismatch")
    
    write_file("grade_prediction.html", content)

# ============================================================
# 2. 修复 mental_risk.html
# ============================================================
def fix_mental_risk():
    content = read_file("mental_risk.html")
    
    # 替换搜索面板
    old_search = '''                <div class="card-body">
                    <input type="text" class="form-control mb-3" id="studentName" placeholder="输入学生姓名">
                    <button class="btn btn-danger w-100" onclick="predictMental()"><i class="bi bi-cpu"></i> 开始预测</button>
                </div>'''
    
    new_search = '''                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">选择班级</label>
                        <select class="form-select" id="classSelect" onchange="onClassChange()">
                            <option value="">-- 选择班级 --</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">选择学生</label>
                        <select class="form-select" id="studentSelect" disabled>
                            <option value="">-- 选择学生 --</option>
                        </select>
                    </div>
                    <button class="btn btn-danger w-100" onclick="predictMental()"><i class="bi bi-cpu"></i> 开始预测</button>
                </div>'''
    
    if old_search in content:
        content = content.replace(old_search, new_search)
        print("  [mental] Search panel replaced")
    else:
        print("  [mental] WARNING: search panel pattern not found")
    
    # 替换 JS
    old_js_mental = '''function predictMental() {
    const name = document.getElementById('studentName').value.trim();
    if (!name) { alert('请输入学生姓名'); return; }

    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';

    fetch(`/search/api?q=${encodeURIComponent(name)}&type=student`)
        .then(r => r.json())
        .then(data => {
            if (data.results && data.results.length > 0) {
                document.getElementById('studentNameSpan').textContent = data.results[0].name;
                return fetch(`/ai-analysis/api/predict/mental-health/${data.results[0].id}`);
            } else { throw new Error('未找到该学生'); }
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            document.getElementById('totalScore').textContent = data.total_score;

            const prob = Math.round(data.risk_probability * 100);
            document.getElementById('riskProb').textContent = prob + '%';
            const badge = document.getElementById('riskLevel');
            if (data.risk_level === 'high') {
                badge.className = 'badge bg-danger fs-6';
                badge.textContent = '🔴 高风险';
            } else if (data.risk_level === 'medium') {
                badge.className = 'badge bg-warning fs-6';
                badge.textContent = '🟡 中风险';
            } else {
                badge.className = 'badge bg-success fs-6';
                badge.textContent = '🟢 低风险';
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}
document.getElementById('studentName').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') predictMental();
});'''
    
    new_js_mental = '''// 班级和学生数据
let studentMapM = {};

function loadClassesM() {
    fetch('/ml/api/classes')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('classSelect');
            sel.innerHTML = '<option value="">-- 选择班级 --</option>';
            (data.classes || []).forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                sel.appendChild(opt);
            });
        });
}

function onClassChangeM() {
    const cid = document.getElementById('classSelect').value;
    const stuSel = document.getElementById('studentSelect');
    stuSel.innerHTML = '<option value="">-- 选择学生 --</option>';
    stuSel.disabled = !cid;
    if (!cid) return;
    
    fetch(`/ml/api/students?class_id=${cid}`)
        .then(r => r.json())
        .then(data => {
            studentMapM[cid] = data.students || [];
            data.students.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                stuSel.appendChild(opt);
            });
            stuSel.disabled = false;
        });
}

function predictMental() {
    const sid = document.getElementById('studentSelect').value;
    if (!sid) { alert('请先选择学生'); return; }
    
    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';
    
    const studentName = document.getElementById('studentSelect').selectedOptions[0].text;
    document.getElementById('studentNameSpan').textContent = studentName;
    
    fetch(`/ai-analysis/api/predict/mental-health/${sid}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            document.getElementById('totalScore').textContent = data.total_score;

            const prob = Math.round(data.risk_probability * 100);
            document.getElementById('riskProb').textContent = prob + '%';
            const badge = document.getElementById('riskLevel');
            if (data.risk_level === 'high') {
                badge.className = 'badge bg-danger fs-6';
                badge.textContent = '🔴 高风险';
            } else if (data.risk_level === 'medium') {
                badge.className = 'badge bg-warning fs-6';
                badge.textContent = '🟡 中风险';
            } else {
                badge.className = 'badge bg-success fs-6';
                badge.textContent = '🟢 低风险';
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}

document.addEventListener('DOMContentLoaded', function() {
    loadClassesM();
});'''
    
    if old_js_mental in content:
        content = content.replace(old_js_mental, new_js_mental)
        print("  [mental] JS replaced")
    else:
        print("  [mental] WARNING: JS pattern not found")
    
    write_file("mental_risk.html", content)

# ============================================================
# 3. 修复 discipline_prediction.html
# ============================================================
def fix_discipline_prediction():
    content = read_file("discipline_prediction.html")
    
    # 替换搜索面板
    old_search = '''                <div class="card-body">
                    <input type="text" class="form-control mb-3" id="studentName" placeholder="输入学生姓名">
                    <button class="btn btn-warning w-100" onclick="predictDiscipline()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    new_search = '''                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">选择班级</label>
                        <select class="form-select" id="classSelect" onchange="onClassChange()">
                            <option value="">-- 选择班级 --</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">选择学生</label>
                        <select class="form-select" id="studentSelect" disabled>
                            <option value="">-- 选择学生 --</option>
                        </select>
                    </div>
                    <button class="btn btn-warning w-100" onclick="predictDiscipline()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    if old_search in content:
        content = content.replace(old_search, new_search)
        print("  [discipline] Search panel replaced")
    else:
        print("  [discipline] WARNING: search panel pattern not found")
    
    # 替换 JS
    old_js_disc = '''function predictDiscipline() {
    const name = document.getElementById('studentName').value.trim();
    if (!name) { alert('请输入学生姓名'); return; }

    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';

    fetch(`/search/api?q=${encodeURIComponent(name)}&type=student`)
        .then(r => r.json())
        .then(data => {
            if (data.results && data.results.length > 0) {
                document.getElementById('studentNameSpan').textContent = data.results[0].name;
                return fetch(`/ai-analysis/api/predict/discipline/${data.results[0].id}`);
            } else { throw new Error('未找到该学生'); }
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.predicted_count_30d === 0 && data.historical_count === 0) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            document.getElementById('histCount').textContent = data.historical_count;
            document.getElementById('dailyRate').textContent = data.daily_rate;
            document.getElementById('predCount').textContent = data.predicted_count_30d;
            const badge = document.getElementById('riskLevel');
            if (data.risk === 'high') {
                badge.className = 'badge bg-danger fs-6';
                badge.textContent = '🔴 高风险（需立即干预）';
            } else if (data.risk === 'medium') {
                badge.className = 'badge bg-warning fs-6';
                badge.textContent = '🟡 中风险（建议关注）';
            } else {
                badge.className = 'badge bg-success fs-6';
                badge.textContent = '🟢 低风险（正常）';
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}
document.getElementById('studentName').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') predictDiscipline();
});'''
    
    new_js_disc = '''// 班级和学生数据
let studentMapD = {};

function loadClassesD() {
    fetch('/ml/api/classes')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('classSelect');
            sel.innerHTML = '<option value="">-- 选择班级 --</option>';
            (data.classes || []).forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                sel.appendChild(opt);
            });
        });
}

function onClassChangeD() {
    const cid = document.getElementById('classSelect').value;
    const stuSel = document.getElementById('studentSelect');
    stuSel.innerHTML = '<option value="">-- 选择学生 --</option>';
    stuSel.disabled = !cid;
    if (!cid) return;
    
    fetch(`/ml/api/students?class_id=${cid}`)
        .then(r => r.json())
        .then(data => {
            studentMapD[cid] = data.students || [];
            data.students.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                stuSel.appendChild(opt);
            });
            stuSel.disabled = false;
        });
}

function predictDiscipline() {
    const sid = document.getElementById('studentSelect').value;
    if (!sid) { alert('请先选择学生'); return; }
    
    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';
    
    const studentName = document.getElementById('studentSelect').selectedOptions[0].text;
    document.getElementById('studentNameSpan').textContent = studentName;
    
    fetch(`/ai-analysis/api/predict/discipline/${sid}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.predicted_count_30d === 0 && data.historical_count === 0) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            document.getElementById('histCount').textContent = data.historical_count;
            document.getElementById('dailyRate').textContent = data.daily_rate;
            document.getElementById('predCount').textContent = data.predicted_count_30d;
            const badge = document.getElementById('riskLevel');
            if (data.risk === 'high') {
                badge.className = 'badge bg-danger fs-6';
                badge.textContent = '🔴 高风险（需立即干预）';
            } else if (data.risk === 'medium') {
                badge.className = 'badge bg-warning fs-6';
                badge.textContent = '🟡 中风险（建议关注）';
            } else {
                badge.className = 'badge bg-success fs-6';
                badge.textContent = '🟢 低风险（正常）';
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}

document.addEventListener('DOMContentLoaded', function() {
    loadClassesD();
});'''
    
    if old_js_disc in content:
        content = content.replace(old_js_disc, new_js_disc)
        print("  [discipline] JS replaced")
    else:
        print("  [discipline] WARNING: JS pattern not found")
    
    write_file("discipline_prediction.html", content)

# ============================================================
# 4. 修复 quality_prediction.html
# ============================================================
def fix_quality_prediction():
    content = read_file("quality_prediction.html")
    
    # 替换搜索面板
    old_search = '''                <div class="card-body">
                    <input type="text" class="form-control mb-3" id="studentName" placeholder="输入学生姓名">
                    <button class="btn btn-info w-100" onclick="predictQuality()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    new_search = '''                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">选择班级</label>
                        <select class="form-select" id="classSelect" onchange="onClassChange()">
                            <option value="">-- 选择班级 --</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">选择学生</label>
                        <select class="form-select" id="studentSelect" disabled>
                            <option value="">-- 选择学生 --</option>
                        </select>
                    </div>
                    <button class="btn btn-info w-100" onclick="predictQuality()">
                        <i class="bi bi-cpu"></i> 开始预测
                    </button>
                </div>'''
    
    if old_search in content:
        content = content.replace(old_search, new_search)
        print("  [quality] Search panel replaced")
    else:
        print("  [quality] WARNING: search panel pattern not found")
    
    # 替换 JS
    old_js_qual = '''function predictQuality() {
    const name = document.getElementById('studentName').value.trim();
    if (!name) { alert('请输入学生姓名'); return; }

    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';

    fetch(`/search/api?q=${encodeURIComponent(name)}&type=student`)
        .then(r => r.json())
        .then(data => {
            if (data.results && data.results.length > 0) {
                document.getElementById('studentNameSpan').textContent = data.results[0].name;
                return fetch(`/ai-analysis/api/predict/quality/${data.results[0].id}`);
            } else { throw new Error('未找到该学生'); }
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            const tbody = document.getElementById('resultsBody');
            tbody.innerHTML = '';
            const dims = data.dimension_predictions || {};
            for (const [dim, pred] of Object.entries(dims)) {
                const trendIcon = pred.trend === 'rising' ? '📈' : (pred.trend === 'declining' ? '📉' : '➡️');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${dim}</td>
                    <td>${pred.historical ? pred.historical.slice(-3).join(', ') + ', ...' : '-'}</td>
                    <td><strong>${pred.predicted}</strong></td>
                    <td>${trendIcon} ${pred.trend === 'rising' ? '上升' : (pred.trend === 'declining' ? '下降' : '稳定')}</td>
                `;
                tbody.appendChild(tr);
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}
document.getElementById('studentName').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') predictQuality();
});'''
    
    new_js_qual = '''// 班级和学生数据
let studentMapQ = {};

function loadClassesQ() {
    fetch('/ml/api/classes')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('classSelect');
            sel.innerHTML = '<option value="">-- 选择班级 --</option>';
            (data.classes || []).forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                sel.appendChild(opt);
            });
        });
}

function onClassChangeQ() {
    const cid = document.getElementById('classSelect').value;
    const stuSel = document.getElementById('studentSelect');
    stuSel.innerHTML = '<option value="">-- 选择学生 --</option>';
    stuSel.disabled = !cid;
    if (!cid) return;
    
    fetch(`/ml/api/students?class_id=${cid}`)
        .then(r => r.json())
        .then(data => {
            studentMapQ[cid] = data.students || [];
            data.students.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                stuSel.appendChild(opt);
            });
            stuSel.disabled = false;
        });
}

function predictQuality() {
    const sid = document.getElementById('studentSelect').value;
    if (!sid) { alert('请先选择学生'); return; }
    
    document.getElementById('loadingArea').style.display = 'block';
    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('noDataArea').style.display = 'none';
    
    const studentName = document.getElementById('studentSelect').selectedOptions[0].text;
    document.getElementById('studentNameSpan').textContent = studentName;
    
    fetch(`/ai-analysis/api/predict/quality/${sid}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingArea').style.display = 'none';
            if (data.code === 1) {
                document.getElementById('noDataArea').style.display = 'block';
                return;
            }
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('studentNameSpan').textContent = data.student_name;
            const tbody = document.getElementById('resultsBody');
            tbody.innerHTML = '';
            const dims = data.dimension_predictions || {};
            for (const [dim, pred] of Object.entries(dims)) {
                const trendIcon = pred.trend === 'rising' ? '📈' : (pred.trend === 'declining' ? '📉' : '➡️');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${dim}</td>
                    <td>${pred.historical ? pred.historical.slice(-3).join(', ') + ', ...' : '-'}</td>
                    <td><strong>${pred.predicted}</strong></td>
                    <td>${trendIcon} ${pred.trend === 'rising' ? '上升' : (pred.trend === 'declining' ? '下降' : '稳定')}</td>
                `;
                tbody.appendChild(tr);
            }
        })
        .catch(err => {
            document.getElementById('loadingArea').style.display = 'none';
            alert('预测失败: ' + err.message);
        });
}

document.addEventListener('DOMContentLoaded', function() {
    loadClassesQ();
});'''
    
    if old_js_qual in content:
        content = content.replace(old_js_qual, new_js_qual)
        print("  [quality] JS replaced")
    else:
        print("  [quality] WARNING: JS pattern not found")
    
    write_file("quality_prediction.html", content)

if __name__ == '__main__':
    print("=== 修复 ML 数学模型预测页面 ===")
    print("")
    
    print("[1/4] 修复 grade_prediction.html...")
    fix_grade_prediction()
    
    print("[2/4] 修复 mental_risk.html...")
    fix_mental_risk()
    
    print("[3/4] 修复 discipline_prediction.html...")
    fix_discipline_prediction()
    
    print("[4/4] 修复 quality_prediction.html...")
    fix_quality_prediction()
    
    print("")
    print("=== 全部完成 ===")
    print("请重启服务: systemctl restart grade7-new")
