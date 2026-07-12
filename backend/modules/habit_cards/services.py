"""
Habit Cards 核心业务服务层

- 教师批量闪击发卡 (issue_cards_to_students)
- 家长盲盒开启 (open_blindbox_for_parent)
- AI 高光少年表彰信自动机 (generate_ai_praise_letter)
"""

import json
import os
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from modules.habit_cards.models import (
    HabitCard, StudentCardWallet, CardTransaction, ParentBlindboxLog,
)

import httpx

# ── DeepSeek 配置 (与 ai_prescription/tasks.py 一致) ──
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxx")
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
            HabitCard.is_active == True,
            HabitCard.school_id == school_id,
        )
    )
    card = card_res.scalar_one_or_none()
    if not card:
        raise ValueError("派发的萌卡模板处于封印或不存在状态")

    now = datetime.now()
    transactions_added = 0

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
    wallet_stmt = select(
        StudentCardWallet, HabitCard
    ).join(
        HabitCard, StudentCardWallet.card_id == HabitCard.id
    ).where(
        StudentCardWallet.school_id == school_id,
        StudentCardWallet.student_id == student_id,
        StudentCardWallet.quantity > 0,
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
        select(ParentBlindboxLog).where(
            ParentBlindboxLog.school_id == school_id,
            ParentBlindboxLog.student_id == student_id,
            ParentBlindboxLog.parent_user_id == parent_user_id,
            ParentBlindboxLog.card_id == card.id,
        ).limit(1)
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
    stmt = select(StudentCardWallet, HabitCard).join(
        HabitCard, StudentCardWallet.card_id == HabitCard.id
    ).where(
        StudentCardWallet.student_id == student_id,
        StudentCardWallet.school_id == school_id,
        StudentCardWallet.quantity > 0,
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
        card_parts.append(
            f"【{card.card_name}】{rarity_cn}级·{category_cn}×{wallet.quantity}次"
        )

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
        except Exception as e:
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
        history.append({
            "id": log.id,
            "card_name": card.card_name,
            "card_rarity": card.card_rarity,
            "card_icon": card.card_icon,
            "opened_at": str(log.opened_at) if log.opened_at else None,
            "is_first_open": is_first,
            "shared_to": log.shared_to,
        })

    return history


async def get_student_wallet_summary(
    db: AsyncSession,
    school_id: int,
    student_id: int,
) -> tuple:
    """
    获取学生钱包摘要: (总卡牌种类数, 总积分)
    """
    stmt = (
        select(
            func.count(StudentCardWallet.id),
            func.coalesce(func.sum(StudentCardWallet.total_points), 0),
        )
        .where(
            StudentCardWallet.school_id == school_id,
            StudentCardWallet.student_id == student_id,
            StudentCardWallet.quantity > 0,
        )
    )
    res = await db.execute(stmt)
    count, points = res.one()
    return (count or 0, points or 0)
