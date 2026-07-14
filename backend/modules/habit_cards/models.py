"""
Habit Cards 数据模型
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


class HabitCard(Base, SchoolMixin):
    """习惯充能卡模板表"""

    __tablename__ = "habit_cards"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    card_code = Column(String(40), nullable=False, comment="模板编码, 如 self_discipline_fox")
    card_name = Column(String(60), nullable=False, comment="卡牌显示名称, 如 自律狐")
    card_category = Column(
        String(20),
        nullable=False,
        comment="habit/academic/social/sports/art",
    )
    card_rarity = Column(
        String(20),
        default="common",
        comment="common/rare/epic/legendary",
    )
    card_icon = Column(String(200), comment="SVG 或 PNG 路径")
    card_description = Column(Text, comment="卡牌描述文案")
    trigger_condition = Column(JSON, comment="AI 触发条件契约")
    reward_points = Column(Integer, default=10, comment="评价积分增量")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_local_now)


class StudentCardWallet(Base, SchoolMixin):
    """学生卡牌钱包表 (高频读写, 支持叠加)"""

    __tablename__ = "student_card_wallets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False)
    card_id = Column(BigInteger, nullable=False)
    quantity = Column(Integer, default=1, comment="持有数量")
    total_points = Column(Integer, default=0, comment="累计获得积分")
    first_earned_at = Column(DateTime)
    last_earned_at = Column(DateTime)


class CardTransaction(Base, SchoolMixin):
    """卡牌发放/消耗流水表"""

    __tablename__ = "card_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False)
    card_id = Column(BigInteger, nullable=False)
    issued_by = Column(BigInteger, nullable=False, comment="教师 user_id")
    transaction_type = Column(
        String(20),
        nullable=False,
        comment="issue/consume/upgrade",
    )
    quantity = Column(Integer, default=1)
    context_type = Column(String(40), comment="触发场景: homework/attendance/behavior")
    context_id = Column(BigInteger)
    note = Column(String(200), comment="教师批注")
    created_at = Column(DateTime, default=get_local_now)


class ParentBlindboxLog(Base, SchoolMixin):
    """家长金色盲盒开启记录表 (运营裂变轴心)"""

    __tablename__ = "parent_blindbox_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False)
    parent_user_id = Column(BigInteger, nullable=False)
    card_id = Column(BigInteger, nullable=False)
    opened_at = Column(DateTime, default=get_local_now)
    shared_to = Column(String(40), comment="裂变追踪: wechat_moments")
