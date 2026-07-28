"""
Habit Cards 核心业务服务层

- 教师批量闪击发卡 (issue_cards_to_students)
- 家长盲盒开启 (open_blindbox_for_parent)
- AI 高光少年表彰信自动机 (generate_ai_praise_letter)
"""

import os
from datetime import datetime

import httpx
from core.db_utils import require_db_url
from core.event_bus import EventBus
from modules.habit_cards.models import (
    CardTransaction,
    HabitCard,
    ParentBlindboxLog,
    StudentCardWallet,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ── DeepSeek 配置 (与 ai_prescription/tasks.py 一致) ──
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")


# ============================================================
# 1. 教师批量发卡引擎
# ============================================================


async def issue_cards_to_students(
    db: AsyncSession,
    school_id: int,
    teacher_id: int,
    card_id: int,
    student_ids: list[int],
    note: str = "",
) -> dict:
    """
    教师批量闪击发卡 — 一个请求向多位学生同时注入卡牌资产。
    流程: 校验卡模板有效性 → 流水线落盘 → 幂等 UPSERT 钱包 → commit
    """
    # 1. 校验卡牌是否合法且在激活态
    card_res = await db.execute(
        select(HabitCard).where(
            HabitCard.id == card_id,
            HabitCard.is_active,
            HabitCard.school_id == school_id,
        )
    )
    card = card_res.scalar_one_or_none()
    if not card:
        raise ValueError("派发的萌卡模板处于封印或不存在状态")

    now = datetime.now()
    transactions_added = 0

    # ── CEP: 查询各学生上期发卡日期，用于沉默检测 ──
    prev_issue_dates: dict[int, datetime] = {}
    for sid in student_ids:
        prev_r = await db.execute(
            select(CardTransaction.created_at)
            .where(
                CardTransaction.student_id == sid,
                CardTransaction.school_id == school_id,
                CardTransaction.transaction_type == "issue",
            )
            .order_by(CardTransaction.created_at.desc())
            .limit(1)
        )
        prev_dt = prev_r.scalar()
        if prev_dt:
            prev_issue_dates[sid] = prev_dt

    for sid in student_ids:
        # 2. 插入发卡流水
        tx = CardTransaction(
            school_id=school_id,
            student_id=sid,
            card_id=card_id,
            issued_by=teacher_id,
            transaction_type="issue",
            quantity=1,
            note=note,
        )
        db.add(tx)

        # 3. UPSERT 学生钱包
        wallet_res = await db.execute(
            select(StudentCardWallet).where(
                StudentCardWallet.school_id == school_id,
                StudentCardWallet.student_id == sid,
                StudentCardWallet.card_id == card_id,
            )
        )
        wallet = wallet_res.scalar_one_or_none()

        if wallet:
            wallet.quantity += 1
            wallet.total_points += card.reward_points
            wallet.last_earned_at = now
        else:
            new_wallet = StudentCardWallet(
                school_id=school_id,
                student_id=sid,
                card_id=card_id,
                quantity=1,
                total_points=card.reward_points,
                first_earned_at=now,
                last_earned_at=now,
            )
            db.add(new_wallet)

        transactions_added += 1

    await db.commit()

    # ── EventBus: 发卡事件泵入成长时间线 + CEP 复合检测 ──
    EventBus().publish(
        "habit_cards.card_issued",
        {
            "school_id": school_id,
            "teacher_id": teacher_id,
            "card_id": card_id,
            "card_name": card.card_name,
            "card_rarity": card.card_rarity,
            "card_category": card.card_category,
            "student_ids": student_ids,
            "issued_count": transactions_added,
            "note": note,
            "occurred_at": now.isoformat(),
        },
    )

    # ── CEP 卡片沉默检测: 后台异步，不阻塞提交返回 ──
    silent_students: list[tuple[int, int]] = []
    for sid, prev_dt in prev_issue_dates.items():
        gap_days = (now - prev_dt).days
        if gap_days > 7:  # 超过7天未获卡视为沉默期
            silent_students.append((sid, gap_days))

    if silent_students:
        import asyncio

        asyncio.create_task(
            _cep_habit_card_silence(
                school_id=school_id,
                teacher_id=teacher_id,
                card_id=card_id,
                card_name=card.card_name,
                silent_students=silent_students,
            )
        )

    return {"status": "success", "issued_count": transactions_added}


# ============================================================
# 2. 家长盲盒开启引擎
# ============================================================


async def open_blindbox_for_parent(
    db: AsyncSession,
    school_id: int,
    parent_user_id: int,
    student_id: int,
) -> dict:
    """
    家长端盲盒翻牌 — 从学生钱包里随机抽一张未开过的卡牌，
    记录开启日志，生成 AI 表彰信。
    """
    # 捞出该生所有卡牌资产
    wallet_stmt = (
        select(StudentCardWallet, HabitCard)
        .join(HabitCard, StudentCardWallet.card_id == HabitCard.id)
        .where(
            StudentCardWallet.school_id == school_id,
            StudentCardWallet.student_id == student_id,
            StudentCardWallet.quantity > 0,
        )
    )
    wallet_res = await db.execute(wallet_stmt)
    wallet_rows = wallet_res.all()

    if not wallet_rows:
        return {
            "status": "empty",
            "card_id": 0,
            "card_name": "等待首充",
            "card_rarity": "common",
            "card_icon": None,
            "is_first_open": True,
            "ai_praise_letter": "小勇士还在修炼中，请等待班主任为他充能第一张卡牌！",
        }

    # 取最高稀有度的卡作为盲盒开出结果（简单策略：稀有度排序）
    rarity_order = {"legendary": 4, "epic": 3, "rare": 2, "common": 1}
    best = max(wallet_rows, key=lambda r: rarity_order.get(r[1].card_rarity, 0))
    wallet, card = best

    # 检查该家长是否首次开启此卡
    blind_check = await db.execute(
        select(ParentBlindboxLog)
        .where(
            ParentBlindboxLog.school_id == school_id,
            ParentBlindboxLog.student_id == student_id,
            ParentBlindboxLog.parent_user_id == parent_user_id,
            ParentBlindboxLog.card_id == card.id,
        )
        .limit(1)
    )
    is_first_open = blind_check.first() is None

    # 记录盲盒开启日志
    blind_log = ParentBlindboxLog(
        school_id=school_id,
        student_id=student_id,
        parent_user_id=parent_user_id,
        card_id=card.id,
    )
    db.add(blind_log)
    await db.commit()

    # ── EventBus: 盲盒开启事件泵入成长时间线 ──
    EventBus().publish(
        "habit_cards.blindbox_opened",
        {
            "school_id": school_id,
            "student_id": student_id,
            "parent_user_id": parent_user_id,
            "card_id": card.id,
            "card_name": card.card_name,
            "card_rarity": card.card_rarity,
            "card_category": card.card_category,
            "is_first_open": is_first_open,
            "occurred_at": datetime.now().isoformat(),
        },
    )

    # 生成 AI 表彰信
    ai_result = await generate_ai_praise_letter(db, student_id, school_id)

    return {
        "status": "success",
        "card_id": card.id,
        "card_name": card.card_name,
        "card_rarity": card.card_rarity,
        "card_icon": card.card_icon,
        "is_first_open": is_first_open,
        "ai_praise_letter": ai_result.get("letter", ""),
    }


# ============================================================
# 3. AI 智能表彰信自动机
# ============================================================


async def generate_ai_praise_letter(
    db: AsyncSession,
    student_id: int,
    school_id: int,
) -> dict:
    """
    DeepSeek 跨界充能 — 抽取学生卡牌资产图谱，
    生成无套话、高情绪价值的《高光少年家校表彰信》
    """
    # 捞出该生钱包里所有卡牌 + 模板信息
    stmt = (
        select(StudentCardWallet, HabitCard)
        .join(HabitCard, StudentCardWallet.card_id == HabitCard.id)
        .where(
            StudentCardWallet.student_id == student_id,
            StudentCardWallet.school_id == school_id,
            StudentCardWallet.quantity > 0,
        )
    )
    res = await db.execute(stmt)
    records = res.all()

    if not records:
        return {"letter": "该同学正在悄悄积攒能量，期待他的第一次卡牌充能！"}

    # 组装卡牌摘要
    card_parts = []
    for wallet, card in records:
        rarity_cn = {
            "legendary": "传说",
            "epic": "史诗",
            "rare": "稀有",
            "common": "普通",
        }.get(card.card_rarity, card.card_rarity)
        category_cn = {
            "habit": "习惯养成",
            "academic": "学业突破",
            "social": "社交品格",
            "sports": "体育精神",
            "art": "艺术素养",
        }.get(card.card_category, card.card_category)
        card_parts.append(f"【{card.card_name}】{rarity_cn}级·{category_cn}×{wallet.quantity}次")

    card_summary = "、".join(card_parts)
    total_points = sum(wallet.total_points for wallet, _ in records)

    prompt = f"""你是 Wings 集团化金牌育人导师。请根据该小学生近期在校斩获的习惯充能卡牌资产，为家长量身定制一封极具情绪价值、画面感温馨的《高光少年家校表彰信》。

【学生荣誉卡牌清单】:
{card_summary}
累计充能积分: {total_points} 分

【硬性契约】:
1. 语气热情、真挚、画面感强，深度赞美孩子的具体闪光行为（结合卡牌种类写细节）。
2. 拒绝任何官话套话，要让家长读完后忍不住想转发朋友圈展示。
3. 控制在 180 字以内，只输出表彰信正文，不加标题前缀。"""

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                LLM_API_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,  # 表彰信用更高温度增加文采
                    "max_tokens": 512,
                },
            )
            if resp.status_code == 200:
                body = resp.json()
                letter = body["choices"][0]["message"]["content"].strip()
                return {"status": "success", "letter": letter}
        except Exception:
            pass  # 兜底文案在调用方处理

    # 兜底：不发空信
    if records:
        top_card = records[0][1]
        return {
            "status": "fallback",
            "letter": (
                f"亲爱的家长：您的孩子近期在校表现令人振奋！"
                f"特别在{top_card.card_name}方面，展现了卓越的成长潜力，"
                f"已累计获得 {total_points} 分成长积分。"
                f"Wings 为他的进步感到骄傲！"
            ),
        }

    return {"letter": "该同学正在悄悄积攒能量，期待他的第一次卡牌充能！"}


# ============================================================
# 4. 盲盒历史查询 (Task #1400)
# ============================================================


async def get_blindbox_history(
    db: AsyncSession,
    school_id: int,
    student_id: int,
    parent_user_id: int,
    limit: int = 20,
) -> list:
    """
    查询家长对该学生的盲盒开启历史，含卡牌名称和稀有度。

    返回: 按 opened_at 倒序的盲盒记录列表
    """
    stmt = (
        select(ParentBlindboxLog, HabitCard)
        .join(HabitCard, ParentBlindboxLog.card_id == HabitCard.id)
        .where(
            ParentBlindboxLog.school_id == school_id,
            ParentBlindboxLog.student_id == student_id,
            ParentBlindboxLog.parent_user_id == parent_user_id,
        )
        .order_by(ParentBlindboxLog.opened_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    rows = res.all()

    history = []
    seen_cards = set()
    for log, card in rows:
        card_key = (card.card_name, card.card_rarity)
        is_first = card_key not in seen_cards
        seen_cards.add(card_key)
        history.append(
            {
                "id": log.id,
                "card_name": card.card_name,
                "card_rarity": card.card_rarity,
                "card_icon": card.card_icon,
                "opened_at": str(log.opened_at) if log.opened_at else None,
                "is_first_open": is_first,
                "shared_to": log.shared_to,
            }
        )

    return history


async def get_student_wallet_summary(
    db: AsyncSession,
    school_id: int,
    student_id: int,
) -> tuple:
    """
    获取学生钱包摘要: (总卡牌种类数, 总积分)
    """
    stmt = select(
        func.count(StudentCardWallet.id),
        func.coalesce(func.sum(StudentCardWallet.total_points), 0),
    ).where(
        StudentCardWallet.school_id == school_id,
        StudentCardWallet.student_id == student_id,
        StudentCardWallet.quantity > 0,
    )
    res = await db.execute(stmt)
    count, points = res.one()
    return (count or 0, points or 0)


# ============================================================
# 5. CEP 卡片沉默检测 → ActiveCompositeAlert + Redis PUBLISH
# ============================================================

SILENCE_THRESHOLD_DAYS = 7  # 沉默阈值: 超过7天未获卡触发预警


async def _cep_habit_card_silence(
    school_id: int,
    teacher_id: int,
    card_id: int,
    card_name: str,
    silent_students: list[tuple[int, int]],  # [(student_id, gap_days), ...]
) -> None:
    """
    CEP 卡片沉默检测 → 创建 ActiveCompositeAlert + Redis PUBLISH 弹窗

    当学生超过7天未获任何萌卡，教师再次发卡时触发预警，
    提醒班主任该生可能存在行为激励断层。

    独立 async session，不阻塞主事务。
    """
    import json as _json
    import logging as _logging
    from datetime import datetime as _dt

    _log = _logging.getLogger(__name__)

    try:
        from core.redis_client import get_redis
        from sqlalchemy import select as _select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        # 独立引擎 (安全: 从环境变量读取，无硬编码回退)
        _DB_URL = require_db_url()
        _engine = create_async_engine(_DB_URL, pool_pre_ping=True, pool_recycle=300, pool_size=2)
        _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

        async with _factory() as db:
            from core.models import Student, User
            from modules.growth.models import ActiveCompositeAlert

            for sid, gap_days in silent_students:
                # 查询学生姓名和班级
                stu_result = await db.execute(
                    _select(Student).where(Student.id == sid, Student.school_id == school_id)
                )
                student = stu_result.scalar_one_or_none()
                if not student:
                    _log.warning("[CEP-HABIT] 学生不存在 | student_id=%s", sid)
                    continue

                # 查询教师姓名
                teacher_result = await db.execute(
                    _select(User.display_name).where(User.id == teacher_id)
                )
                teacher_name = teacher_result.scalar() or "未知教师"

                # ── Wings 3.2: 分布式冷却锁 — 3天内同一学生不重复告警 ──
                COOLDOWN_TTL = 259_200  # 3 天
                redis = get_redis()
                if redis:
                    cooldown_key = f"wings:cep:lock:habit_silence:{sid}"
                    try:
                        acquired = await redis.set(cooldown_key, "1", ex=COOLDOWN_TTL, nx=True)
                    except Exception:
                        acquired = False  # Redis 异常 → 放行（宁重复不丢失）
                    if not acquired:
                        _log.info(
                            "[CEP-HABIT] 冷却锁未获取, 3天内已触发过 | student=%s",
                            sid,
                        )
                        continue

                title = f"卡片沉默预警: {student.name} 已 {gap_days} 天未获萌卡"

                meta = _json.dumps(
                    {
                        "module": "habit_cards",
                        "alert_source": "HABIT_CARD_SILENCE",
                        "student_id": sid,
                        "student_name": student.name,
                        "class_id": getattr(student, "class_id", None),
                        "teacher_id": teacher_id,
                        "teacher_name": teacher_name,
                        "card_id": card_id,
                        "card_name": card_name,
                        "silence_days": gap_days,
                        "threshold_days": SILENCE_THRESHOLD_DAYS,
                        "triggered_at": _dt.utcnow().isoformat(),
                    },
                    ensure_ascii=False,
                    default=str,
                )

                alert = ActiveCompositeAlert(
                    school_id=school_id,
                    student_id=sid,
                    alert_type="HABIT_CARD_SILENCE",
                    title=title[:200],
                    reason_meta=meta,
                    ai_prescription=(
                        f"## 萌卡沉默预警\n\n"
                        f"**学生**: {student.name}\n"
                        f"**沉默天数**: {gap_days} 天（阈值: {SILENCE_THRESHOLD_DAYS} 天）\n"
                        f"**触发卡牌**: {card_name}\n\n"
                        f"### 诊断分析\n"
                        f"该生已连续 {gap_days} 天未获得行为激励卡牌，"
                        f"可能存在以下情况:\n"
                        f"1. 行为表现处于低谷期，需要教师关注和正向引导\n"
                        f"2. 激励体系对该生吸引力下降，建议更换卡牌类型\n"
                        f"3. 教师发卡频率不足，建议增加日常观察\n\n"
                        f"### 处置建议\n"
                        f"1. 班主任安排一次简短谈心，了解学生近期状态\n"
                        f"2. 在日常教学中主动发现学生的闪光点并即时发卡\n"
                        f"3. 可尝试使用不同主题的萌卡重新激活学生兴趣\n"
                        f"4. 关注该生在其他维度（学业/考勤/心理）的同步变化\n"
                    ),
                    is_resolved=False,
                )
                db.add(alert)
                await db.commit()
                await db.refresh(alert)

                _log.info(
                    "[CEP-HABIT] ActiveCompositeAlert 已创建 | alert_id=%s student=%s silence=%dd",
                    alert.id,
                    sid,
                    gap_days,
                )

                # Redis PUBLISH 弹窗
                redis = get_redis()
                if redis:
                    popup_data = {
                        "type": "composite_alert",
                        "alert_type": "HABIT_CARD_SILENCE",
                        "school_id": school_id,
                        "student_id": sid,
                        "alert_id": alert.id,
                        "title": f"🔔 萌卡沉默预警: {student.name}",
                        "summary": f"{student.name} 已 {gap_days} 天未获行为激励卡牌，教师 {teacher_name} 刚刚为其补发了 [{card_name}]",
                        "silence_days": gap_days,
                        "card_name": card_name,
                        "created_at": _dt.utcnow().isoformat(),
                    }
                    await redis.publish(
                        "wings:notifications:popup",
                        _json.dumps(popup_data, ensure_ascii=False),
                    )
                    _log.info("[CEP-HABIT] SSE弹窗已广播 | student=%s silence=%dd", sid, gap_days)

    except Exception as e:
        _log.error("[CEP-HABIT] 卡片沉默处理失败: %s", e, exc_info=True)
