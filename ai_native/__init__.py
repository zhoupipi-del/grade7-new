"""
ai_native — WINGS AI Native 2.1 Control Plane
==============================================

Root package for AI Native 2.1 (v3.2 FINAL).

Canonical directory boundary:
    ai_native/                       — Control Plane (本包，仓库根，无 backend/ 前缀)
        governance/                  — DataClassification / ResourceScope / ApprovalPolicy
        runtime/                     — ToolDescriptor / Executor / Agent
        models/                      — SQLAlchemy ORM（9 表）

    modules/ai_teacher_assistant/    — 业务 Tool（Slice 1 落地处，依赖 ai_native.*）

Phase A/B0 已锁定（v3.2 FINAL Schema Contract Frozen）；Phase B1 起进入施工。

★ 本包由 alembic/env.py 自动扫描并加载到 Base.metadata（详见 env.py）。
★ 严禁从业务模块向 ai_native/ 反向 import。
"""

__version__ = "2.1-b1"
__canonical__ = "v3.2 FINAL"