"""
心理咨询预约与工作台 数据模型

三表物理契约:
  psy_consultable_slots   — 心理老师开放的可预约时间标尺
  psy_appointments        — 预约申请流水表 (学生自荐/班主任转介)
  psy_consult_records     — 硬核加密咨询记录表 (心理老师专属写实)

隐私切面:
  encrypted_clog 字段在服务层通过 Fernet 对称加密落地，
  仅心理老师(counselor role)和高阶德育风控官(MS_ADMIN)可解密读取。
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)


class PsyConsultableSlot(Base, SchoolMixin):
    """心理老师开放的可预约时间槽位标尺"""

    __tablename__ = "psy_consultable_slots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_id = Column(BigInteger, nullable=False, comment="心理老师 user_id")
    date = Column(DateTime, nullable=False, comment="开放日期")
    start_time = Column(String(10), nullable=False, comment="开始时间 HH:MM")
    end_time = Column(String(10), nullable=False, comment="结束时间 HH:MM")
    location = Column(String(100), comment="咨询地点(咨询室/线上)")
    max_capacity = Column(Integer, default=1, comment="该时段最大容纳人数")
    current_booked = Column(Integer, default=0, comment="当前已预约人数")
    status = Column(
        String(20),
        default="open",
        comment="open(开放)/booked(已约)/locked(锁定)",
    )
    week_pattern = Column(
        String(10),
        default="every",
        comment="every/odd/even — 单双周模式",
    )
    is_recurring = Column(Boolean, default=False, comment="是否每周重复")
    created_at = Column(DateTime, default=get_local_now)


class PsyAppointment(Base, SchoolMixin):
    """预约申请流水表 — 学生自荐或班主任转介心理老师"""

    __tablename__ = "psy_appointments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="被咨询学生 ID")
    applicant_id = Column(BigInteger, nullable=False, comment="发起人 user_id(学生本人或班主任)")
    slot_id = Column(BigInteger, nullable=False, comment="关联 psy_consultable_slots.id")
    source = Column(
        String(20),
        nullable=False,
        comment="self(学生自荐)/teacher(班主任转介)/parent(家长申请)",
    )
    reason_summary = Column(
        String(200),
        comment="申请理由摘要(脱敏后可展示)",
    )
    status = Column(
        String(20),
        default="pending",
        comment="pending/confirmed/cancelled/completed/no_show",
    )
    risk_flag = Column(
        String(10),
        default="green",
        comment="当前风险色标: green/yellow/orange/red",
    )
    counselor_note = Column(
        String(300),
        comment="心理老师审核备注",
    )
    created_at = Column(DateTime, default=get_local_now)
    confirmed_at = Column(DateTime, comment="心理老师确认时间")
    completed_at = Column(DateTime, comment="咨询完成时间")


class PsyConsultRecord(Base, SchoolMixin):
    """硬核加密咨询记录表 — 心理老师专属工作台写实"""

    __tablename__ = "psy_consult_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id = Column(BigInteger, nullable=False, comment="关联 psy_appointments.id")
    student_id = Column(BigInteger, nullable=False, comment="冗余: 被咨询学生 ID")
    counselor_id = Column(BigInteger, nullable=False, comment="心理咨询师 user_id")

    # ── 加密核心字段 ──
    encrypted_clog = Column(
        Text,
        comment="Fernet 加密的咨询日志正文 — 仅 counselor+MS_ADMIN 可解密",
    )
    # ── 明文元数据 (用于索引/统计但不泄露隐私) ──
    risk_level = Column(
        String(10),
        default="green",
        comment="风险评级: green(无)/yellow(关注)/orange(预警)/red(危机)",
    )
    consult_category = Column(
        String(30),
        comment="咨询分类: emotion/interpersonal/academic/family/self_harm/other",
    )
    is_crisis = Column(Boolean, default=False, comment="是否触发危机干预")
    is_referred = Column(Boolean, default=False, comment="是否转介外部医院/机构")
    referral_target = Column(String(200), comment="转介医院/机构名称")
    followup_date = Column(DateTime, comment="计划下次随访日期")
    session_duration_min = Column(Integer, comment="本次咨询时长(分钟)")

    # ── 审计追踪 ──
    encryption_version = Column(
        String(10),
        default="v1",
        comment="加密算法版本标识(支持密钥轮换)",
    )
    decryption_access_log = Column(
        JSON,
        default=list,
        comment="解密访问审计: [{user_id, role, ts}]",
    )
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)
