#!/usr/bin/env python3
"""Patch dashboard.html UI to match survey/analysis.html style (A+ grade)"""
import re

path = '/opt/grade7-new/templates/ai_analysis/dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Step 1: Wrap in extends block (original is a partial template, no extends)
if '{%' not in html[:5]:
    html = '{% extends "base.html" %}\n{% block title %}全景德育总账 - 梨江中学德育管理平台{% endblock %}\n\n{% block extra_css %}\n<style>\n  .stat-card { border:none; border-radius:12px; padding:16px 12px; text-align:center; transition:transform .2s,box-shadow .2s; box-shadow:0 2px 8px rgba(0,0,0,.08); color:#fff; }\n  .stat-card:hover { transform:translateY(-3px); box-shadow:0 6px 20px rgba(0,0,0,.12); }\n  .stat-card .stat-num { font-size:1.8rem; font-weight:700; }\n  .stat-card .stat-label { font-size:.82rem; margin-top:2px; opacity:.85; }\n  .filter-bar { background:#f8f9fa; border-radius:10px; padding:12px 20px; display:flex; align-items:center; gap:14px; flex-wrap:wrap; }\n  .filter-bar .form-label { font-size:.82rem; }\n  #student-table th { font-size:.82rem; white-space:nowrap; }\n  #student-table td { font-size:.88rem; vertical-align:middle; }\n  #student-table tbody tr:hover { background:rgba(37,99,235,.04)!important; }\n  .empty-state { text-align:center; padding:60px 20px; color:#adb5bd; }\n  .empty-state i { font-size:3.5rem; display:block; margin-bottom:16px; }\n</style>\n{% endblock %}\n\n{% block content %}\n' + html + '\n{% endblock %}'

# Step 2: Change title
html = html.replace('统一仪表盘', '全景德育总账')
html = html.replace('bi-grid-3x3-gap-fill', 'bi-archive')

# Step 3: Replace stat cards - change from border-* style to gradient stat-card
card_map = [
    ('card border-primary', 'stat-card', 'background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);', 'text-primary', 'color:#fff;'),
    ('card border-info', 'stat-card', 'background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);', 'text-info', 'color:#fff;'),
    ('card border-success', 'stat-card', 'background:linear-gradient(135deg,#43e97b 0%,#38f9d7 100%);', 'text-success', 'color:#1a1a2e;'),
    ('card border-warning', 'stat-card', 'background:linear-gradient(135deg,#ffd89b 0%,#19547b 100%);', 'text-warning', 'color:#fff;'),
    ('card border-danger', 'stat-card', 'background:linear-gradient(135deg,#ff6a6a 0%,#ee0979 100%);', 'text-danger', 'color:#fff;'),
    ('card border-secondary', 'stat-card', 'background:linear-gradient(135deg,#a8edea 0%,#fed6e3 100%);', 'text-secondary', 'color:#1a1a2e;'),
]

for old_class, new_class, gradient, old_color, new_color in card_map:
    # Replace: <div class="card border-primary"><div class="card-body text-center py-2">
    # With: <div class="stat-card" style="..."><div class="card-body text-center py-2">
    html = html.replace(
        f'<div class="{old_class}"><div class="card-body text-center py-2">',
        f'<div class="{new_class}" style="{gradient}"><div class="card-body text-center py-2">'
    )
    # Replace color class on numbers
    html = html.replace(f'fw-bold {old_color}', f'fw-bold {new_color}')

# Step 4: Replace filter section card -> filter-bar div
html = html.replace(
    '<div class="card mb-3">\n  <div class="card-body py-2">',
    '<div class="filter-bar mb-3">'
)
html = html.replace(
    '    </div>\n  </div>\n</div>\n\n<!-- 学生总账表格 -->',
    '</div>\n\n<!-- 学生总账表格 -->'
)

# Step 5: Replace table card -> border-0 shadow-sm
html = html.replace(
    '<div class="card">\n  <div class="card-header',
    '<div class="card border-0 shadow-sm" style="border-radius:12px;">\n  <div class="card-header'
)
html = html.replace(
    '</div>\n</div>\n\n<script>',
    '</div>\n</div>\n\n<script>'
)

# Step 6: Add funnel icon to filter bar
if 'bi-funnel' not in html:
    html = html.replace(
        '<div class="filter-bar mb-3">',
        '<div class="filter-bar mb-3">\n  <i class="bi bi-funnel text-muted"></i>'
    )

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Patched {len(html)} chars successfully!')
