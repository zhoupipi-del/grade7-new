"""
modules/red_flag — 流动红旗三维加权引擎

班级维度的流动红旗评优系统，跨模块整合：
  - RoutineScore（班主任/年级组/德育处三方评分）
  - attendance_records（考勤异常扣分熔断）
  - discipline_records（违纪扣分熔断）

流程: 数据录入 → 生成草稿(三维加权) → 审核发布 → 归档快照
"""
