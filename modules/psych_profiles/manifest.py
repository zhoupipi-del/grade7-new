"""
psych_profiles — 心理档案 + 筛查流水 + 双轨预警 Nexus

物理表:
  psy_profiles            — 学生心理综合档案 (一学生一档案)
  psy_screening_records   — 量表筛查流水快照

核心引擎:
  rdi_psy_nexus — 学业x心理双轨预警合成视图
    联表: risk_warnings (RDI四维) + student_risk_alerts (Z-Score学业)
         + psy_profiles (心理) + psy_screening_records (筛查)

隐私切面:
  - 档案 tags/notes 为明文 (非敏感元数据)
  - 敏感咨询内容由 psych_counseling 模块的 Fernet 加密保护
  - 筛查原始分 raw_scores 为 JSON 明文, 访问受角色门禁限制
  - nexus 端点输出合成预警, 不暴露咨询内容原文

角色门禁:
  - 写操作: MS_ADMIN / counselor / GRADE_LEADER
  - 读操作: MS_ADMIN / counselor / GRADE_LEADER / CLASS_TEACHER
"""

MODULE_CODE = "psych_profiles"
MODULE_NAME = "心理档案与双轨预警"
MODULE_CATEGORY = "wellness"
MODULE_DEPENDENCIES = ["psych_screening", "psych_counseling"]
ENABLED_BY_DEFAULT = True

MODULE_PHASES = ["junior", "senior", "integrated", "primary"]


def register(router_prefix="/api/v1/psych-profiles"):
    from modules.psych_profiles.routers import router
    return router, router_prefix
