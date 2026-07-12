"""
Habit Cards Pydantic 模型
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ============================================================
# 卡牌模板
# ============================================================

class CardTemplateOut(BaseModel):
    id: int
    card_code: str
    card_name: str
    card_category: str
    card_rarity: str
    card_icon: Optional[str] = None
    card_description: Optional[str] = None
    reward_points: int
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================
# 发卡请求
# ============================================================

class IssueCardsRequest(BaseModel):
    school_id: int
    teacher_id: int
    card_id: int
    student_ids: List[int]
    note: Optional[str] = ""

    class Config:
        from_attributes = True


class IssueCardsResponse(BaseModel):
    status: str
    issued_count: int


# ============================================================
# 学生钱包
# ============================================================

class WalletItemOut(BaseModel):
    card_id: int
    card_name: str
    card_code: str
    card_icon: Optional[str] = None
    card_rarity: str
    card_category: str
    quantity: int
    total_points: int
    first_earned_at: Optional[datetime] = None
    last_earned_at: Optional[datetime] = None


class WalletResponse(BaseModel):
    status: str
    student_id: int
    wallet: List[WalletItemOut]
    ai_praise_letter: str


# ============================================================
# 盲盒开启
# ============================================================

class BlindBoxOpenRequest(BaseModel):
    parent_user_id: int
    student_id: int
    school_id: int

    class Config:
        from_attributes = True


class BlindBoxOpenResponse(BaseModel):
    status: str
    card_id: int
    card_name: str
    card_rarity: str
    card_icon: Optional[str] = None
    is_first_open: bool
    ai_praise_letter: str


# ============================================================
# 家长盲盒 H5 落地页 (Task #1400)
# ============================================================

class ParentBlindboxResponse(BaseModel):
    """家长盲盒翻牌响应 — 含学生信息, 供 H5 渲染"""
    status: str                              # success / empty
    student_name: str                        # 学生姓名 (用于页面标题)
    card_id: int
    card_name: str
    card_rarity: str                         # legendary/epic/rare/common
    card_icon: Optional[str] = None
    card_category: Optional[str] = None      # 卡牌类别: 德育/智育/体育/美育/劳育
    is_first_open: bool
    ai_praise_letter: str                    # DeepSeek 表彰信正文
    total_cards: int                         # 该生总卡牌资产数
    total_points: int                        # 该生总积分


class BlindboxHistoryItem(BaseModel):
    """盲盒历史记录条目"""
    id: int
    card_name: str
    card_rarity: str
    card_icon: Optional[str] = None
    opened_at: Optional[str] = None
    is_first_open: bool
    shared_to: Optional[str] = None          # 裂变渠道


class BlindboxHistoryResponse(BaseModel):
    """盲盒历史记录列表"""
    status: str
    student_id: int
    student_name: str
    history: List[BlindboxHistoryItem]


class ShareBlindboxRequest(BaseModel):
    """记录家长分享行为"""
    log_id: int                              # 盲盒日志 ID
    shared_to: str                           # 分享渠道: wechat_moments/wechat_friend/qq/save_image
