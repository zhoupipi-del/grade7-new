"""
Habit Cards 路由层

端点:
  GET  /templates              — 获取全校卡牌模板库
  POST /issue                  — 教师批量闪击发卡
  GET  /wallet/{student_id}    — 调阅学生钱包 + AI 表彰信
  POST /blindbox/open          — 家长盲盒翻牌
  GET  /transactions/{student_id} — 学生发卡流水
  GET  /parent/blindbox        — 家长 H5 盲盒自动翻牌 (Task #1400)
  GET  /parent/blindbox/history — 盲盒开启历史 (Task #1400)
  POST /parent/blindbox/share   — 裂变分享标记 (Task #1400)
"""

from core.models import Student, User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, status
from modules.habit_cards.models import (
    CardTransaction,
    HabitCard,
    ParentBlindboxLog,
    StudentCardWallet,
)
from modules.habit_cards.schemas import (
    BlindboxHistoryItem,
    BlindboxHistoryResponse,
    BlindBoxOpenRequest,
    BlindBoxOpenResponse,
    CardTemplateOut,
    IssueCardsRequest,
    IssueCardsResponse,
    ParentBlindboxResponse,
    ShareBlindboxRequest,
    WalletItemOut,
    WalletResponse,
)
from modules.habit_cards.services import (
    generate_ai_praise_letter,
    get_blindbox_history,
    get_student_wallet_summary,
    issue_cards_to_students,
    open_blindbox_for_parent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["habit-cards"])


# ============================================================
# GET /templates — 获取全校活跃卡牌模板
# ============================================================


@router.get("/templates", response_model=dict)
async def list_card_templates(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """拉取当前学校所有启用的卡牌模板"""
    # 多租户安全: 只能查自己学校的模板
    effective_school_id = current_user.school_id
    if current_user.role != "MS_ADMIN":
        school_id = effective_school_id

    stmt = (
        select(HabitCard)
        .where(
            HabitCard.school_id == school_id,
            HabitCard.is_active == True,
        )
        .order_by(HabitCard.card_rarity.desc(), HabitCard.card_name)
    )
    res = await db.execute(stmt)
    cards = res.scalars().all()

    return {
        "status": "success",
        "cards": [CardTemplateOut.from_orm(c).model_dump() for c in cards],
    }


# ============================================================
# POST /issue — 教师批量闪击发卡
# ============================================================


@router.post("/issue", response_model=IssueCardsResponse)
async def batch_issue_cards(
    payload: IssueCardsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER, UserRole.TEACHER)),
):
    """教师端点：批量向选定学生派发萌卡"""
    # RBAC: 只有教师和管理员可以发卡
    # RBAC: 教师/班主任/年级组长/管理员可发卡
    allowed = {"ms_admin", "grade_leader", "class_teacher", "teacher"}
    if (current_user.role or "").lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师和管理员可以派发卡牌",
        )

    try:
        result = await issue_cards_to_students(
            db=db,
            school_id=current_user.school_id,
            teacher_id=current_user.id,
            card_id=payload.card_id,
            student_ids=payload.student_ids,
            note=payload.note,
        )
        return IssueCardsResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================
# GET /wallet/{student_id} — 学生卡牌钱包 + AI 表彰信
# ============================================================


@router.get("/wallet/{student_id}", response_model=WalletResponse)
async def get_student_wallet(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """调阅学生卡牌钱包及 AI 即时表彰信"""
    school_id = current_user.school_id

    stmt = (
        select(StudentCardWallet, HabitCard)
        .join(HabitCard, StudentCardWallet.card_id == HabitCard.id)
        .where(
            StudentCardWallet.student_id == student_id,
            StudentCardWallet.school_id == school_id,
            StudentCardWallet.quantity > 0,
        )
        .order_by(
            StudentCardWallet.last_earned_at.desc(),
        )
    )

    res = await db.execute(stmt)
    rows = res.all()

    wallet_data = []
    for wallet, card in rows:
        wallet_data.append(
            WalletItemOut(
                card_id=card.id,
                card_name=card.card_name,
                card_code=card.card_code,
                card_icon=card.card_icon,
                card_rarity=card.card_rarity,
                card_category=card.card_category,
                quantity=wallet.quantity,
                total_points=wallet.total_points,
                first_earned_at=wallet.first_earned_at,
                last_earned_at=wallet.last_earned_at,
            ).model_dump()
        )

    # 生成 AI 表彰信
    ai_result = await generate_ai_praise_letter(db, student_id, school_id)

    return WalletResponse(
        status="success",
        student_id=student_id,
        wallet=wallet_data,
        ai_praise_letter=ai_result.get("letter", ""),
    )


# ============================================================
# POST /blindbox/open — 家长盲盒翻牌
# ============================================================


@router.post("/blindbox/open", response_model=BlindBoxOpenResponse)
async def open_blindbox(
    payload: BlindBoxOpenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.PARENT)),
):
    """家长端点：盲盒翻牌查看孩子最新卡牌资产"""
    # 多租户安全
    school_id = current_user.school_id

    try:
        result = await open_blindbox_for_parent(
            db=db,
            school_id=school_id,
            parent_user_id=current_user.id,
            student_id=payload.student_id,
        )
        return BlindBoxOpenResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"盲盒开启熔断: {e}",
        )


# ============================================================
# GET /transactions/{student_id} — 发卡流水
# ============================================================


@router.get("/transactions/{student_id}")
async def get_card_transactions(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """查看学生的发卡流水记录"""
    school_id = current_user.school_id

    stmt = (
        select(CardTransaction)
        .where(
            CardTransaction.student_id == student_id,
            CardTransaction.school_id == school_id,
        )
        .order_by(CardTransaction.created_at.desc())
        .limit(50)
    )

    res = await db.execute(stmt)
    txs = res.scalars().all()

    return {
        "status": "success",
        "student_id": student_id,
        "transactions": [
            {
                "id": tx.id,
                "card_id": tx.card_id,
                "issued_by": tx.issued_by,
                "transaction_type": tx.transaction_type,
                "note": tx.note,
                "created_at": str(tx.created_at) if tx.created_at else None,
            }
            for tx in txs
        ],
    }


# ============================================================
# 家长盲盒 H5 落地页 依赖与端点 (Task #1400)
# ============================================================


async def require_parent_binding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple:
    """
    家长角色 + 绑定校验铁闸。

    规则:
      1. 必须是 PARENT 角色
      2. bound_student_id 不能为 NULL
      3. 返回 (User, Student) 元组，供后续端点直接使用
    """
    role = (current_user.role or "").lower()
    if role != "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅家长角色可访问此端点",
        )

    if current_user.bound_student_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="家长账号未绑定学生，请联系班主任完成绑定",
        )

    # 加载学生信息
    stmt = select(Student).where(
        Student.id == current_user.bound_student_id,
        Student.school_id == current_user.school_id,
    )
    res = await db.execute(stmt)
    student = res.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="绑定的学生不存在或已离校",
        )

    return current_user, student


# ── GET /parent/blindbox: H5 盲盒自动翻牌 ──


@router.get("/parent/blindbox", response_model=ParentBlindboxResponse)
async def parent_auto_blindbox(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.PARENT)),
):
    """家长 H5 落地页自动盲盒翻牌 — 无需传参, 自动识别绑定学生"""
    # 绑定校验
    parent_user, student = await require_parent_binding(
        current_user=current_user,
        db=db,
    )

    try:
        result = await open_blindbox_for_parent(
            db=db,
            school_id=current_user.school_id,
            parent_user_id=current_user.id,
            student_id=student.id,
        )

        # 获取钱包摘要
        total_cards, total_points = await get_student_wallet_summary(
            db,
            current_user.school_id,
            student.id,
        )

        return ParentBlindboxResponse(
            status=result["status"],
            student_name=student.name,
            card_id=result["card_id"],
            card_name=result["card_name"],
            card_rarity=result["card_rarity"],
            card_icon=result.get("card_icon"),
            card_category=None,  # open_blindbox 返回里暂不含 category
            is_first_open=result["is_first_open"],
            ai_praise_letter=result["ai_praise_letter"],
            total_cards=total_cards,
            total_points=total_points,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"盲盒开启熔断: {e}",
        )


# ── GET /parent/blindbox/history: 盲盒历史 ──


@router.get("/parent/blindbox/history", response_model=BlindboxHistoryResponse)
async def parent_blindbox_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.PARENT)),
):
    """家长查看盲盒开启历史记录 (最近 20 条)"""
    parent_user, student = await require_parent_binding(
        current_user=current_user,
        db=db,
    )

    history = await get_blindbox_history(
        db=db,
        school_id=current_user.school_id,
        student_id=student.id,
        parent_user_id=current_user.id,
        limit=20,
    )

    return BlindboxHistoryResponse(
        status="success",
        student_id=student.id,
        student_name=student.name,
        history=[BlindboxHistoryItem(**item) for item in history],
    )


# ── POST /parent/blindbox/share: 裂变分享标记 ──


@router.post("/parent/blindbox/share")
async def parent_mark_share(
    payload: ShareBlindboxRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.PARENT)),
):
    """家长分享盲盒表彰信后标记裂变渠道"""
    parent_user, student = await require_parent_binding(
        current_user=current_user,
        db=db,
    )

    # 查找盲盒日志并标记 shared_to
    stmt = select(ParentBlindboxLog).where(
        ParentBlindboxLog.id == payload.log_id,
        ParentBlindboxLog.school_id == current_user.school_id,
        ParentBlindboxLog.parent_user_id == current_user.id,
    )
    res = await db.execute(stmt)
    log = res.scalar_one_or_none()

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="盲盒记录不存在",
        )

    log.shared_to = payload.shared_to
    await db.commit()

    return {
        "status": "success",
        "message": f"已记录分享渠道: {payload.shared_to}",
    }
