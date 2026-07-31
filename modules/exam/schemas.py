"""
modules/exam/schemas.py — Pydantic 请求/响应模型

覆盖端点:
- 考试科目安排: SubjectCreate / SubjectUpdate / SubjectOut / SubjectItem
- 考场管理:     RoomCreate / RoomUpdate / RoomOut / RoomItem
- 考试安排:     ArrangementCreate / ArrangementUpdate / ArrangementOut
- 座位分配:     SeatAssignRequest / SeatAssignmentOut / SeatOverrideUpdate
- 监考安排:     InvigilatorCreate / InvigilatorOut
- 录入窗口:     EntryWindowCreate / EntryWindowOut / EntryWindowProgress
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal


# ═══════════════════════════════════════════════════════
# 考试科目安排
# ═══════════════════════════════════════════════════════

class SubjectScheduleCreate(BaseModel):
    """创建考试科目安排"""
    exam_id: int = Field(..., description="考试ID")
    subject_id: int = Field(..., description="科目ID")
    exam_date: date = Field(..., description="考试日期")
    start_time: Optional[time] = Field(default=None, description="开始时间 (如 08:00)")
    end_time: Optional[time] = Field(default=None, description="结束时间 (如 09:30)")
    full_score: Optional[Decimal] = Field(default=None, description="本次考试满分 (NULL=取科目默认)")
    sort_order: int = Field(default=0, description="排序")


class SubjectScheduleUpdate(BaseModel):
    """更新考试科目安排"""
    exam_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    full_score: Optional[Decimal] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class SubjectScheduleOut(BaseModel):
    """考试科目安排响应"""
    id: int
    exam_id: int
    subject_id: int
    exam_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    full_score: Optional[Decimal] = None
    is_active: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════
# 考场管理
# ═══════════════════════════════════════════════════════

class RoomCreate(BaseModel):
    """创建考场"""
    room_name: str = Field(..., min_length=1, max_length=50, description="考场名称")
    room_code: Optional[str] = Field(default=None, max_length=30, description="考场编号")
    building: Optional[str] = Field(default=None, max_length=50, description="楼栋")
    floor: Optional[int] = Field(default=None, description="楼层")
    capacity: int = Field(default=30, ge=1, le=500, description="可用座位数")
    room_type: str = Field(default="classroom", description="类型: classroom/hall/lab")
    class_id: Optional[int] = Field(default=None, description="关联班级ID (NULL=公共考场)")


class RoomUpdate(BaseModel):
    """更新考场"""
    room_name: Optional[str] = Field(default=None, max_length=50)
    room_code: Optional[str] = Field(default=None, max_length=30)
    building: Optional[str] = Field(default=None, max_length=50)
    floor: Optional[int] = None
    capacity: Optional[int] = Field(default=None, ge=1, le=500)
    room_type: Optional[str] = None
    is_active: Optional[bool] = None


class RoomOut(BaseModel):
    """考场响应"""
    id: int
    room_name: str
    room_code: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[int] = None
    capacity: int
    room_type: str
    class_id: Optional[int] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoomItem(BaseModel):
    """考场列表项（精简版）"""
    id: int
    room_name: str
    room_code: Optional[str] = None
    capacity: int
    room_type: str
    is_active: bool

    class Config:
        from_attributes = True


class RoomSeedRequest(BaseModel):
    """从班级表自动生成考场"""
    class_ids: Optional[list[int]] = Field(default=None, description="指定班级ID列表 (NULL=全部活跃班级)")
    capacity: int = Field(default=45, ge=1, le=500, description="默认座位数")


class RoomSeedResult(BaseModel):
    """考场自动生成结果"""
    created: int = Field(..., description="新增考场数")
    skipped: int = Field(..., description="已存在跳过数")
    room_ids: list[int] = Field(default=[], description="新增考场ID列表")


# ═══════════════════════════════════════════════════════
# 考试安排（排考）
# ═══════════════════════════════════════════════════════

class ArrangementCreate(BaseModel):
    """创建考试安排（科目×考场×时间段）"""
    exam_id: int = Field(..., description="考试ID")
    subject_id: int = Field(..., description="科目ID")
    room_id: int = Field(..., description="考场ID")
    exam_date: date = Field(..., description="考试日期")
    start_time: time = Field(..., description="开始时间")
    end_time: time = Field(..., description="结束时间")
    notes: Optional[str] = Field(default=None, max_length=200, description="备注")


class ArrangementUpdate(BaseModel):
    """更新考试安排"""
    exam_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    notes: Optional[str] = Field(default=None, max_length=200)


class ArrangementOut(BaseModel):
    """考试安排响应"""
    id: int
    exam_id: int
    subject_id: int
    room_id: int
    exam_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArrangementWithDetail(BaseModel):
    """考试安排响应（含考场名称等关联信息）"""
    id: int
    exam_id: int
    subject_id: int
    room_id: int
    room_name: str = Field(..., description="考场名称")
    exam_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None


# ═══════════════════════════════════════════════════════
# 座位分配
# ═══════════════════════════════════════════════════════

class SeatAssignRequest(BaseModel):
    """批量编排座位请求

    arrangement_method:
    - random:     随机混编，打乱后顺序填入考场
    - serpentine: 蛇形按总分排名分配，防优生扎堆
    """
    exam_id: int = Field(..., description="考试ID")
    subject_id: int = Field(..., description="科目ID")
    arrangement_method: str = Field(default="random", description="编排方式: random/serpentine")
    room_ids: Optional[list[int]] = Field(default=None, description="指定考场列表 (NULL=该科目所有已安排考场)")
    class_ids: Optional[list[int]] = Field(default=None, description="指定参考班级 (NULL=全年级)")


class SeatAssignResult(BaseModel):
    """座位编排结果"""
    exam_id: int
    subject_id: int
    method: str
    total_assigned: int = Field(..., description="总分配座位数")
    rooms_used: int = Field(..., description="使用考场数")
    manual_overrides_preserved: int = Field(..., description="保留的人工覆盖座位数")


class SeatAssignmentOut(BaseModel):
    """座位分配响应"""
    id: int
    exam_id: int
    subject_id: int
    student_id: int
    room_id: int
    seat_number: int
    arrangement_method: str
    is_manual_override: bool
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SeatAssignmentDetail(SeatAssignmentOut):
    """座位分配详情（含学生姓名、考场名）"""
    student_name: str = Field(..., description="学生姓名")
    room_name: str = Field(..., description="考场名称")


class SeatOverrideUpdate(BaseModel):
    """手动修改座位（补丁3: 设为 is_manual_override=1）

    用于特殊需求：伤残/视力障碍/靠门第一排等。
    修改后算法重排时跳过此座位。
    """
    room_id: int = Field(..., description="新考场ID")
    seat_number: int = Field(..., ge=1, description="新座位号")
    remark: Optional[str] = Field(default=None, max_length=200, description="备注 (如 骨折/视力障碍)")


# ═══════════════════════════════════════════════════════
# 监考安排
# ═══════════════════════════════════════════════════════

class InvigilatorCreate(BaseModel):
    """指派监考教师

    ⚠️ 补丁2: 同一教师同一时段不可被指派到两个不同考场
       services 层会做时间重叠检测，冲突时返回 409。
    """
    exam_id: int = Field(..., description="考试ID")
    subject_id: int = Field(..., description="科目ID")
    room_id: int = Field(..., description="考场ID")
    user_id: int = Field(..., description="监考教师用户ID")
    role: str = Field(default="chief", description="监考角色: chief(主)/assistant(副)")
    exam_date: date = Field(..., description="考试日期")
    start_time: time = Field(..., description="开始时间")
    end_time: time = Field(..., description="结束时间")
    notes: Optional[str] = Field(default=None, max_length=200, description="备注")


class InvigilatorOut(BaseModel):
    """监考安排响应"""
    id: int
    exam_id: int
    subject_id: int
    room_id: int
    user_id: int
    role: str
    exam_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InvigilatorDetail(InvigilatorOut):
    """监考安排详情（含教师姓名、考场名）"""
    user_name: str = Field(..., description="教师姓名")
    room_name: str = Field(..., description="考场名称")


class InvigilatorConflictOut(BaseModel):
    """监考冲突信息"""
    existing_id: int
    existing_exam_id: int
    existing_room_id: int
    existing_room_name: str
    existing_start_time: time
    existing_end_time: time
    conflict_type: str = Field(..., description="冲突类型: time_overlap")


# ═══════════════════════════════════════════════════════
# 成绩录入窗口
# ═══════════════════════════════════════════════════════

class EntryWindowCreate(BaseModel):
    """创建成绩录入窗口

    ⚠️ 补丁1: class_id 可为 NULL
       NULL = 全校该科目通开（粗粒度）
       非NULL = 精确到班级
    """
    exam_id: int = Field(..., description="考试ID")
    subject_id: int = Field(..., description="科目ID")
    class_id: Optional[int] = Field(default=None, description="班级ID (NULL=全校该科通开)")


class EntryWindowOut(BaseModel):
    """录入窗口响应"""
    id: int
    exam_id: int
    subject_id: int
    class_id: Optional[int] = None
    status: str
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    opened_by: Optional[int] = None
    closed_by: Optional[int] = None
    entry_count: int
    expected_count: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EntryWindowProgress(BaseModel):
    """录入进度"""
    exam_id: int
    subject_id: int
    total_windows: int
    open_windows: int
    closed_windows: int
    pending_windows: int
    total_entry_count: int
    total_expected_count: Optional[int] = None
    completion_rate: Optional[float] = Field(default=None, description="完成率%")


class EntryWindowBulkCreateRequest(BaseModel):
    """批量创建录入窗口 — 为一场考试的所有科目×所有班级批量创建"""
    exam_id: int = Field(..., description="考试ID")
    class_ids: Optional[list[int]] = Field(default=None, description="班级ID列表 (NULL=全年级所有班级)")
    school_wide: bool = Field(default=False, description="是否创建全校通开窗口 (class_id=NULL)")


class EntryWindowBulkCreateResult(BaseModel):
    """批量创建结果"""
    exam_id: int
    created: int
    skipped: int
    window_ids: list[int] = Field(default=[])
