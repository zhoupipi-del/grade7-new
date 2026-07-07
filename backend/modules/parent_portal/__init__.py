"""
modules/parent_portal — Wings 3.0 家长门户（只读聚合网关 + 反馈/申诉独立写操作）

架构定位:
  - 聚合网关: 仪表盘/孩子概览直连 evaluation/attendance/behavior/risk_models/growth Service 内部方法
  - 独立写操作: parent_feedbacks（双向闭环反馈）+ parent_appeals_proxy（申诉代理追踪）
  - 越权铁闸: parent_id → bound_student_id 绑定校验（绝对红线）

端点清单 (7):
  GET    /parent_portal/dashboard              — 家长仪表盘聚合
  GET    /parent_portal/child/overview         — 孩子五维+考勤+违纪+风险概览
  POST   /parent_portal/feedbacks              — 提交反馈
  GET    /parent_portal/feedbacks              — 反馈列表
  GET    /parent_portal/feedbacks/{id}         — 反馈详情
  POST   /parent_portal/feedbacks/{id}/reply   — 处理反馈（班主任/德育处）
  POST   /parent_portal/appeals/proxy          — 申诉代理（Facade路由到discipline/behavior）
"""
