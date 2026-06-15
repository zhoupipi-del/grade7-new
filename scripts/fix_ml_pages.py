#!/usr/bin/env python3
"""修复 ml_models 的4个预测页面：把"输入姓名搜索"改成"班级+学生下拉选择器"
参考 growth_prediction.html 的交互模式
"""
import os

TEMPLATE_DIR = "/opt/grade7-new/templates/ml_models"

def fix_grade_prediction():
    """成绩预测 - 改成下拉选择"""
    html = """{% block extra_js %}
<script>
let studentMap = {};  // class_id -> [students]

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

document.addEventListener('DOMContentLoaded', function() {
    loadClasses();
    document.getElementById('classSelect').addEventListener('change', onClassChange);
});
</script>
{% endblock %}
"""
    return html

print("Script created successfully")
print("This is a template generator - need to integrate with actual template files")
