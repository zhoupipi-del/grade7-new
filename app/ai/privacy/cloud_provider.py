"""WINGS AI Privacy — CloudStudentDataProvider（Step 0 适配器声明）。

源: WINGS Secure Fabric BASELINE FINAL v1.0 FROZEN / Step 0 / D

接线状态（诚实记录，Step 0 不接线）：
------------------------------------------------------------------
契约要求 "PrivacyGateway → StudentDataProvider → CloudStudentDataProvider
→ 原来的数据/service"，且 "CloudStudentDataProvider 只做适配器，
严禁重写 SQL/ORM/语义"。

WINGS 现状（2026-08-16 只读侦察）：
- PrivacyGateway（core/privacy_gateway.py）本身就是纯脱敏/审计层，
  不持有 DB 直连、不取学生数据——六条硬约束中的 "Gateway 不持有 DB
  直连" 已天然满足。
- CF-03 真实取数点在 AIPrescriptionAggregator.build_student_context
  （modules/ai_prescription/aggregator.py:75），跨 13 路数据源
  （behavior/discipline/evaluation/attendance/red_flag/psych/growth/
  homework/error_funnel/psych_profiles/psych_counseling ...），
  各路均为**内嵌 SQL**，无独立可复用函数。
- 冲突原因：Provider 契约接口（get_behavior_events / get_attendance /
  get_grades / get_psych_risk，单类数据门面 + student_token）与
  aggregator 的 13 路聚合上下文**不同构**；把 aggregator 塞进四方法
  会改变上下文语义/时间窗口/排序（违反契约 D 的不得改语义约束）。

结论：Step 0 只落地接口与适配器声明（本文件），不接线、不重写
现有查询。接线需在 Edge 阶段由 EdgeStudentDataProvider 需求驱动，
届时以真实 Edge 数据源 shape 重新评估。等价性测试因此为 N/A
（未发生 refactor，无前后对比对象）。
------------------------------------------------------------------
"""

from datetime import datetime

from app.ai.privacy.base import StudentDataProvider


class CloudStudentDataProvider(StudentDataProvider):
    """Cloud 阶段适配器声明。

    NOT_WIRED（Step 0）: 方法签名已就位；内部实现留待 Edge 阶段接线。
    不重写现有 SQL —— 现有取数保持 AIPrescriptionAggregator 原样。
    """

    async def get_behavior_events(
        self,
        student_token: str,
        days: int = 30,
    ) -> list[dict]:
        """目标接线点: aggregator.py:147 behavior_records 路。
        冲突: aggregator 内嵌 SQL + 聚合统计，非单类事件门面。"""
        raise NotImplementedError(
            "CloudStudentDataProvider NOT_WIRED (Step 0) — "
            "见 app/edge/README.md §CloudStudentDataProvider"
        )

    async def get_attendance(
        self,
        student_token: str,
        days: int = 30,
    ) -> dict:
        """目标接线点: aggregator.py 内嵌 AttendanceRecord 查询。同上。"""
        raise NotImplementedError(
            "CloudStudentDataProvider NOT_WIRED (Step 0) — "
            "见 app/edge/README.md §CloudStudentDataProvider"
        )

    async def get_grades(
        self,
        student_token: str,
        days: int = 90,
    ) -> list[dict]:
        """目标接线点: aggregator.py 内嵌成绩查询。同上。"""
        raise NotImplementedError(
            "CloudStudentDataProvider NOT_WIRED (Step 0) — "
            "见 app/edge/README.md §CloudStudentDataProvider"
        )

    async def get_psych_risk(
        self,
        student_token: str,
    ) -> dict:
        """目标接线点: aggregator.py psych_deep 路。
        返回边界严格遵循契约 C: 仅 risk_level + trend + confirmed。"""
        raise NotImplementedError(
            "CloudStudentDataProvider NOT_WIRED (Step 0) — "
            "见 app/edge/README.md §CloudStudentDataProvider"
        )
