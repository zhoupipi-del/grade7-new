"""
core/privacy_audit.py — 敏感数据访问审计（CF-02, ⑤.5 Compliance Foundation V1）

目的：
  为心理类敏感数据（psych_profiles / psych_screening / psych_counseling 等）的
  每一次「读 / 写 / 越权尝试」留下不可抵赖的账本，回答：
    - 谁（user_id）在什么时间（created_at）访问了哪个学生（student_id）的什么资源（resource_type）
    - 是合法放行（allowed）还是被拦截（denied）
    - 访问的用途（purpose）—— 由后端根据端点语义自动填，调用方不可伪造

设计纪律（稳定 > 先进）：
  - 审计写操作**独立提交**：复用请求会话 db，但显式 db.add + db.commit，
    使审计行在请求后续失败/回滚时依然落库（get_db_override 先 commit 再 yield，
    异常时 rollback 只回滚「本次提交之后」的新事务，不影响已提交的审计行）。
  - best-effort：审计自身任何异常都吞掉并打 warning，绝不影响业务请求。
  - 不引入新的外部依赖、不触碰其他模块，仅依赖 core.models 的 Base/SchoolMixin。
  - purpose 只允许后端常量传入，无 request 字段，杜绝调用方伪造用途。
"""

import inspect
import logging
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.exc import SQLAlchemyError

from fastapi import HTTPException

from core.models import Base, SchoolMixin, get_local_now


logger = logging.getLogger("wings.privacy_audit")


# ─────────────────────────────────────────────────────────────
# 常量：访问结果 / 用途枚举（用途仅允许后端常量，禁止调用方传入）
# ─────────────────────────────────────────────────────────────
ACCESS_ALLOWED = "allowed"
ACCESS_DENIED = "denied"
ACCESS_ERROR = "error"

# purpose 用途枚举（后端自动填，不可由客户端伪造）
PURPOSE_SCREENING_REVIEW = "screening_review"   # 筛查复盘
PURPOSE_CASE_FOLLOWUP = "case_followup"         # 个案跟进
PURPOSE_CRISIS_RESPONSE = "crisis_response"     # 危机干预响应
PURPOSE_STUDENT_SUPPORT = "student_support"     # 学生支持/日常关注
PURPOSE_AUTHORIZED_EXPORT = "authorized_export" # 授权导出
PURPOSE_SECURITY_AUDIT = "security_audit"       # 安全/合规审计
PURPOSE_DEFAULT = PURPOSE_STUDENT_SUPPORT


# ─────────────────────────────────────────────────────────────
# ORM 模型
# ─────────────────────────────────────────────────────────────
class SensitiveDataAccessLog(Base, SchoolMixin):
    """敏感数据访问审计日志 — 谁在何时以何种用途访问了哪个学生的敏感资源"""

    __tablename__ = "sensitive_data_access_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="操作人 user_id")
    student_id = Column(
        BigInteger, nullable=True, index=True,
        comment="被访问学生ID；列表/聚合场景可为 NULL",
    )
    resource_type = Column(
        String(40), nullable=False,
        comment="资源类型: psych_profile/psych_screening/psych_assessment/"
                "psych_intervention/psych_consult_record/psych_appointment/...",
    )
    resource_id = Column(
        String(80), nullable=True,
        comment="资源标识: 具体业务ID 或 'scope'(聚合/列表场景)",
    )
    action = Column(
        String(30), nullable=False,
        comment="read_detail/read_list/write/export/...",
    )
    purpose = Column(
        String(40), nullable=False,
        comment="用途枚举（后端自动填，调用方不可伪造）",
    )
    purpose_note = Column(Text, nullable=True, comment="可选用途备注（后端自动填）")
    scope_type = Column(
        String(20), nullable=True,
        comment="访问者作用域: school/grade/class/student/null",
    )
    scope_id = Column(BigInteger, nullable=True, comment="scope 对应 id")
    result = Column(
        String(20), nullable=False,
        comment="allowed/denied/error",
    )
    detail = Column(Text, nullable=True, comment="拒绝原因 / 异常摘要")
    created_at = Column(DateTime, default=get_local_now, nullable=False)

    __table_args__ = (
        Index("idx_sdal_user", "school_id", "user_id", "created_at"),
        Index("idx_sdal_student", "school_id", "student_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────
def _derive_scope(user) -> tuple:
    """从当前用户推导其作用域类型/编号，用于审计 scope_type/scope_id。"""
    role = getattr(user, "role", None)
    role = role.value if hasattr(role, "value") else (role or "")
    role = role.lower() if isinstance(role, str) else ""
    if role == "class_teacher":
        return "class", getattr(user, "class_id", None)
    if role == "grade_leader":
        return "grade", getattr(user, "grade_id", None)
    if role in ("ms_admin", "counselor"):
        return "school", None
    return None, None


# ─────────────────────────────────────────────────────────────
# 对外 API
# ─────────────────────────────────────────────────────────────
async def log_access(
    db,
    *,
    user_id: int,
    school_id: int,
    student_id: int | None = None,
    resource_type: str,
    resource_id: str | None = None,
    action: str,
    purpose: str,
    purpose_note: str | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
    result: str,
    detail: str | None = None,
) -> None:
    """写下一条敏感访问审计记录。best-effort：任何异常都吞掉并打 warning。

    注意：本函数会 db.add + db.commit，使审计行独立提交、不受调用方
    后续 rollback 影响。调用方应传入**请求会话 db**（与生产 get_db_override 一致）。
    """
    try:
        rec = SensitiveDataAccessLog(
            school_id=school_id,
            user_id=user_id,
            student_id=student_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            purpose=purpose,
            purpose_note=purpose_note,
            scope_type=scope_type,
            scope_id=scope_id,
            result=result,
            detail=detail,
        )
        db.add(rec)
        await db.commit()
    except SQLAlchemyError as e:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("[PRIVACY_AUDIT] log_access SQLAlchemyError: %s", e)
    except Exception as e:  # noqa: BLE001 — 审计失败绝不影响业务
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("[PRIVACY_AUDIT] log_access unexpected error: %s", e)


async def guard_and_audit(
    db,
    current_user,
    student_id: int | None,
    check_coro,
    *,
    resource_type: str,
    action: str,
    purpose: str,
    resource_id: str | None = None,
) -> object | None:
    """执行一次敏感访问的归属/越权校验，并把结果（放行/拒绝）写入审计。

    Args:
        db: 请求会话（FastAPI Depends(get_db)）
        current_user: 当前登录用户（含 role / class_id / grade_id / school_id）
        student_id: 被访问学生ID（聚合/列表场景为 None）
        check_coro: 零参可调用对象，返回协程或值；其内部应执行真实的行级校验
                    （如 get_student_or_403 / _verify_student_scope）。校验抛
                    HTTPException(403/404) 视为越权拒绝。传 None 表示不做行级校验
                    （仅记录一次 scope 级访问）。
        resource_type / action / purpose: 审计元数据（purpose 由后端常量传入）
        resource_id: 资源标识，缺省时取 student_id 或 'scope'

    Returns:
        check_coro 的返回值（如 get_student_or_403 返回的 Student 对象）。

    Raises:
        原样 re-raise check_coro 抛出的 HTTPException（拒绝已先行写审计）。
    """
    scope_type, scope_id = _derive_scope(current_user)
    rid = resource_id or (str(student_id) if student_id is not None else "scope")

    try:
        check_result = None
        if check_coro is not None:
            res = check_coro()
            check_result = await res if inspect.isawaitable(res) else res
    except HTTPException as e:
        # 403/404 视为越权/不存在性拒绝，均记为 denied（不区分以避免存在性探测）
        if e.status_code in (403, 404):
            await log_access(
                db,
                user_id=current_user.id,
                school_id=current_user.school_id,
                student_id=student_id,
                resource_type=resource_type,
                resource_id=rid,
                action=action,
                purpose=purpose,
                scope_type=scope_type,
                scope_id=scope_id,
                result=ACCESS_DENIED,
                detail=str(e.detail),
            )
        raise
    except Exception as e:  # noqa: BLE001 — 校验逻辑本身异常也记一条 error
        await log_access(
            db,
            user_id=current_user.id,
            school_id=current_user.school_id,
            student_id=student_id,
            resource_type=resource_type,
            resource_id=rid,
            action=action,
            purpose=purpose,
            scope_type=scope_type,
            scope_id=scope_id,
            result=ACCESS_ERROR,
            detail=f"{type(e).__name__}: {e}",
        )
        raise

    # 放行：记 allowed
    await log_access(
        db,
        user_id=current_user.id,
        school_id=current_user.school_id,
        student_id=student_id,
        resource_type=resource_type,
        resource_id=rid,
        action=action,
        purpose=purpose,
        scope_type=scope_type,
        scope_id=scope_id,
        result=ACCESS_ALLOWED,
    )
    return check_result
