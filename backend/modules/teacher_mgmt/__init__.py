"""
teacher_mgmt — 教师管理模块

提供教师创建、列表查询、教师详情、扩展信息维护、
任教学科分配、工作量统计、角色分配(双重角色解耦overlay)、
有效角色集合解析等功能。

核心功能:
  create_teacher        — 创建教师 (User+Teacher+Extension一步到位)
  list_teachers         — 教师列表
  get_teacher_detail    — 教师详情
  upsert_extension      — 扩展信息维护
  assign_subjects       — 任教学科分配
  workload CRUD         — 工作量统计
  role assignment CRUD  — 角色分配(双重角色解耦overlay)
  resolve_effective_roles — 有效角色集合(排课+审批+大盘三切面)
"""
