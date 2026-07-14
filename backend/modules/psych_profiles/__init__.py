"""
psych_profiles 模块 — 心理档案 + 筛查流水 + 学业x心理双轨预警 Nexus

数据链路:
  psych_screening (量表题库/答题/干预) ─┐
  psych_counseling (预约/加密咨询记录) ─┼─→ psy_profiles (综合档案)
  risk_models (RDI四维预警)            ─┤    ↓
  data_adapter (Z-Score学业预警)       ─┘  rdi_psy_nexus (双轨合成)
                                           ↓
                                    comprehensive-risks API
                                    → co_trigger / action_priority

安全声明:
  本模块不存储任何加密咨询内容原文 (由 psych_counseling 模块 Fernet 加密保护)。
  psy_profiles.tags 和 notes 字段为明文元数据, 设计上仅存非敏感信息。
  psy_screening_records.raw_scores 为量表因子原始分, 属于中等敏感数据,
  通过角色门禁 (require_psych_read/write) 限制访问。
"""

from modules.psych_profiles.manifest import (
    ENABLED_BY_DEFAULT,
    MODULE_CATEGORY,
    MODULE_CODE,
    MODULE_DEPENDENCIES,
    MODULE_NAME,
    MODULE_PHASES,
    register,
)

__all__ = [
    "MODULE_CODE",
    "MODULE_NAME",
    "MODULE_CATEGORY",
    "MODULE_DEPENDENCIES",
    "ENABLED_BY_DEFAULT",
    "MODULE_PHASES",
    "register",
]
