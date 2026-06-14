"""梨江中学德育管理平台 — 数据模型"""
import json
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ── 角色枚举 ──
ROLES = {
    "ms_admin": "德育处管理员",
    "grade_leader": "年级组长",
    "class_teacher": "班主任",
    "teacher": "普通教师",
    "parent": "家长",
    "student": "学生",
}


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher", index=True)
    grade_id = db.Column(db.Integer, nullable=True)   # 年级组长/班主任绑定
    class_id = db.Column(db.Integer, nullable=True)    # 班主任绑定
    bound_student_id = db.Column(db.Integer, nullable=True)  # 家长绑定孩子
    phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, pw):
        # 10000次迭代：内部管理系统兼顾速度（5ms）与安全，login体验流畅
        self.password_hash = generate_password_hash(pw, method="pbkdf2:sha256:10000", salt_length=8)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "role_label": ROLES.get(self.role, self.role),
            "grade_id": self.grade_id,
            "class_id": self.class_id,
            "is_active": self.is_active,
        }


class Grade(db.Model):
    __tablename__ = "grades"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    classes = db.relationship("Class", backref="grade", lazy="dynamic")


class Class(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    head_teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    student_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    students = db.relationship("Student", backref="class_", lazy="dynamic")


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    student_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    gender = db.Column(db.String(4), default="男")
    id_card = db.Column(db.String(18), nullable=True)
    national_id = db.Column(db.String(20), nullable=True)   # 全国学籍号
    ethnicity = db.Column(db.String(20), default="汉族")
    birth_date = db.Column(db.Date, nullable=True)
    address = db.Column(db.String(200), nullable=True)
    parent1_name = db.Column(db.String(64), nullable=True)
    parent1_phone = db.Column(db.String(20), nullable=True)
    parent1_relation = db.Column(db.String(20), nullable=True)
    parent2_name = db.Column(db.String(64), nullable=True)
    parent2_phone = db.Column(db.String(20), nullable=True)
    parent2_relation = db.Column(db.String(20), nullable=True)
    primary_school = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    enrolled_at = db.Column(db.Date, nullable=True)
    tags = db.Column(db.Text, default="")                    # 逗号分隔标签，如"优等生,班干部,重点关注"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def tags_list(self):
        """返回标签列表（从逗号分隔字符串解析）"""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


# ── 德育任务 ──
class Task(db.Model):
    """德育处→年级组→班主任 任务流转"""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    from_role = db.Column(db.String(20), nullable=False)       # ms_admin / grade_leader
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)      # grade / class / all
    target_id = db.Column(db.Integer, nullable=True)            # grade_id 或 class_id
    status = db.Column(db.String(20), default="pending")        # pending / assigned / done / closed
    deadline = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    from_user = db.relationship("User", foreign_keys=[from_user_id], lazy="joined")


class TaskFeedback(db.Model):
    """任务反馈/回复"""
    __tablename__ = "task_feedbacks"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("Task", backref=db.backref("feedbacks", lazy="selectin"), lazy="joined")
    user = db.relationship("User", lazy="joined")


# ── 违纪记录 ──
class DisciplineRecord(db.Model):
    __tablename__ = "discipline_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False)          # warning/minor/major/serious
    category = db.Column(db.String(40), nullable=True)        # 打架/吸烟/迟到/仪容/课堂/其他
    description = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, nullable=True)          # 处理措施
    points = db.Column(db.Integer, default=0)                  # 扣分
    status = db.Column(db.String(20), default="active")       # active / resolved / appealed
    verify_status = db.Column(db.String(20), default='DRAFT', index=True)  # 状态机: DRAFT/VERIFIED
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", backref=db.backref("discipline_records", lazy="selectin"), lazy="joined")
    creator = db.relationship("User", foreign_keys=[created_by], lazy="joined")


# ── 纪律申诉 ──
class DisciplineAppeal(db.Model):
    __tablename__ = "discipline_appeals"

    id = db.Column(db.Integer, primary_key=True)
    discipline_id = db.Column(db.Integer, db.ForeignKey("discipline_records.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)    # 家长
    reason = db.Column(db.Text, nullable=False)                                        # 申诉理由
    status = db.Column(db.String(20), default="pending")                               # pending/reviewing/approved/rejected
    review_comment = db.Column(db.Text, nullable=True)                                 # 复核意见
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)      # 复核人
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    discipline = db.relationship("DisciplineRecord", backref=db.backref("appeals", lazy="selectin", cascade="all, delete-orphan"), lazy="joined")
    student = db.relationship("Student", lazy="joined")
    applicant = db.relationship("User", foreign_keys=[applicant_id], lazy="joined")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by], lazy="joined")


# ── 常规评分 ──
class RoutineScore(db.Model):
    __tablename__ = "routine_scores"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)       # 卫生/纪律/两操/礼仪/自习
    score = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text, nullable=True)
    inspector = db.Column(db.String(64), nullable=True)
    record_date = db.Column(db.Date, default=date.today, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── 考勤 ──
class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)          # present / late / early / absent / leave
    record_date = db.Column(db.Date, default=date.today, index=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── 请假 ──
class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)  # 申请人（家长/学生）
    reason = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="pending")      # pending / class_approved / grade_approved / rejected
    class_approved_by = db.Column(db.Integer, nullable=True)
    class_approved_at = db.Column(db.DateTime, nullable=True)
    grade_approved_by = db.Column(db.Integer, nullable=True)
    grade_approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", lazy="joined")
    applicant = db.relationship("User", foreign_keys=[applicant_id], lazy="joined")


# ── 问题学生 ──
class ProblemStudent(db.Model):
    __tablename__ = "problem_students"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)       # 心理/家庭/行为/学习/身体/混合
    level = db.Column(db.String(10), default="yellow")         # red / yellow
    description = db.Column(db.Text, nullable=False)
    intervention = db.Column(db.Text, nullable=True)           # 干预措施
    status = db.Column(db.String(20), default="active")        # active / monitoring / resolved
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("problem_records", lazy="selectin"), lazy="joined")


# ── 问题学生跟踪记录 ──
class ProblemTrack(db.Model):
    __tablename__ = "problem_tracks"

    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problem_students.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    problem = db.relationship("ProblemStudent", backref=db.backref("tracks", lazy="selectin"), lazy="joined")


# ── 消息 ──
class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # NULL=系统消息
    to_user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), default="通用")   # 违纪通知/成绩通知/家长会/活动通知/请假通知/表扬/通用
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    from_user = db.relationship("User", foreign_keys=[from_user_id], lazy="joined")
    recipient  = db.relationship("User", foreign_keys=[to_user_id], lazy="joined")


# ── 公告 ──
class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(64), nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    target_roles = db.Column(db.String(200), nullable=True)   # 逗号分隔，空=全部
    expire_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── 五翼评价（精简，从旧系统迁移核心字段） ──
class WingsScore(db.Model):
    __tablename__ = "wings_scores"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    dimension = db.Column(db.String(40), nullable=False)       # 德/智/体/美/劳
    score = db.Column(db.Float, default=0)
    scorer_type = db.Column(db.String(20), nullable=False)     # teacher/parent/self/peer
    scorer_id = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── 心理问卷 ──
class PsychSurvey(db.Model):
    __tablename__ = "psych_surveys"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    survey_type = db.Column(db.String(40), default="MSSMHS-55")  # 问卷类型
    answers_json = db.Column(db.Text, nullable=False)           # JSON格式55题答案
    total_score = db.Column(db.Float, nullable=True)
    dimensions_json = db.Column(db.Text, nullable=True)         # 各维度得分JSON
    is_valid = db.Column(db.Boolean, default=True)              # 测谎校验
    verify_status = db.Column(db.String(20), default='PENDING', index=True)  # 状态机: PENDING/COMPLETED
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════
#  Block 1 新增模型 — 成绩/通知/评语/家长会
# ══════════════════════════════════════════════════════════════

class Subject(db.Model):
    """科目"""
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)
    full_score = db.Column(db.Float, default=100.0)
    pass_score = db.Column(db.Float, default=60.0)
    sort_order = db.Column(db.Integer, default=0)


class Exam(db.Model):
    """考试"""
    __tablename__ = "exams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    exam_date = db.Column(db.Date, default=date.today)
    exam_type = db.Column(db.String(20), default="月考")       # 月考/期中/期末/模拟
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    grade = db.relationship("Grade", lazy="joined")
    scores = db.relationship("Score", backref="exam", lazy="dynamic", cascade="all, delete-orphan")


class Score(db.Model):
    """考试成绩"""
    __tablename__ = "scores"
    __table_args__ = (
        db.UniqueConstraint("student_id", "exam_id", "subject_id", name="uq_score_student_exam_subject"),
    )
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, default=0.0)
    verify_status = db.Column(db.String(20), default='DRAFT', index=True)  # 状态机: DRAFT/VERIFIED
    rank_class = db.Column(db.Integer, default=0)
    rank_grade = db.Column(db.Integer, default=0)

    student = db.relationship("Student", lazy="joined")
    subject = db.relationship("Subject", lazy="joined")


class Notice(db.Model):
    """通知公告（含回执追踪）"""
    __tablename__ = "notices"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default="")
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)  # NULL=全年级
    grade_id = db.Column(db.Integer, nullable=True)
    require_receipt = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.String(50), default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    target_class = db.relationship("Class", backref=db.backref("notices", lazy="selectin"), lazy="joined")
    receipts = db.relationship("NoticeReceipt", backref="notice", lazy="dynamic", cascade="all, delete-orphan")


class NoticeReceipt(db.Model):
    """通知回执"""
    __tablename__ = "notice_receipts"
    __table_args__ = (
        db.UniqueConstraint("notice_id", "student_id", name="uq_notice_receipt"),
    )
    id = db.Column(db.Integer, primary_key=True)
    notice_id = db.Column(db.Integer, db.ForeignKey("notices.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    status = db.Column(db.String(10), default="unread")       # unread/read/signed
    read_at = db.Column(db.DateTime, nullable=True)
    signed_at = db.Column(db.DateTime, nullable=True)
    signed_by = db.Column(db.String(30), default="")

    student = db.relationship("Student", lazy="joined")


class EndTermComment(db.Model):
    """期末评语"""
    __tablename__ = "endterm_comments"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.String(20), nullable=False)             # 2025-2026-1
    overall_comment = db.Column(db.Text, default="")                # 综合评语
    strengths = db.Column(db.Text, default="")                      # 优点
    improvements = db.Column(db.Text, default="")                   # 待改进
    teacher_suggestion = db.Column(db.Text, default="")             # 教师建议
    status = db.Column(db.String(20), default="draft")              # draft/published
    created_by = db.Column(db.String(50), default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("endterm_comments", lazy="selectin"), lazy="joined")


class ParentMeeting(db.Model):
    """家长会管理"""
    __tablename__ = "parent_meetings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    meeting_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=True)            # HH:MM
    end_time = db.Column(db.String(10), nullable=True)
    location = db.Column(db.String(100), default="")
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False)
    target_classes = db.Column(db.Text, default="[]")               # JSON数组班级ID
    description = db.Column(db.Text, default="")
    organizer = db.Column(db.String(50), default="")
    status = db.Column(db.String(20), default="planned")            # planned/ongoing/completed
    created_by = db.Column(db.String(50), default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grade = db.relationship("Grade", lazy="joined")
    signins = db.relationship("ParentMeetingSignin", backref="meeting", lazy="dynamic", cascade="all, delete-orphan")


class ParentMeetingSignin(db.Model):
    """家长会签到"""
    __tablename__ = "parent_meeting_signins"
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("parent_meetings.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    parent_name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), default="")
    is_late = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, default="")
    signin_time = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", lazy="joined")


# ══════════════════════════════════════════════════════════════
#  Block 2 新增模型 — 家访/标签/审计
# ══════════════════════════════════════════════════════════════

class HomeVisit(db.Model):
    """家访记录"""
    __tablename__ = "home_visits"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    visit_date = db.Column(db.Date, nullable=False)
    visit_type = db.Column(db.String(20), default="上门家访")       # 上门家访/电话家访/来校面谈/线上沟通/其他
    content_summary = db.Column(db.Text, default="")
    parent_feedback = db.Column(db.Text, default="")
    teacher_name = db.Column(db.String(50), default="")
    follow_up = db.Column(db.Text, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("home_visits", lazy="selectin"), lazy="joined")
    creator = db.relationship("User", foreign_keys=[created_by_id], lazy="joined")


class AuditLog(db.Model):
    """操作审计日志"""
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), default="")
    action = db.Column(db.String(50), nullable=False)               # CREATE/UPDATE/DELETE
    target_type = db.Column(db.String(30), nullable=False)           # Student/Score/Exam/Discipline
    target_id = db.Column(db.Integer, default=0)
    detail = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════
#  Block 3 新增模型 — 综合素质评价 / 活动管理 / 消息模板
# ══════════════════════════════════════════════════════════════

class QualityIndicator(db.Model):
    """综合素质评价指标（五维 + 二级指标）"""
    __tablename__ = "quality_indicators"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    parent_id = db.Column(db.Integer, default=0)             # 0=一级指标, >0=二级指标
    dimension = db.Column(db.String(30), nullable=True)       # 一级维度标识: moral/academic/health/art/social
    weight = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=100.0)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class QualityScore(db.Model):
    """综合素质评价评分记录"""
    __tablename__ = "quality_scores"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=False)
    grade_id = db.Column(db.Integer, nullable=False)
    indicator_id = db.Column(db.Integer, db.ForeignKey("quality_indicators.id"), nullable=False)
    score = db.Column(db.Float, default=0.0)
    scorer_type = db.Column(db.String(20), nullable=False)          # self/peer/teacher/parent
    scorer_id = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", lazy="joined")
    indicator = db.relationship("QualityIndicator", lazy="joined")


class Activity(db.Model):
    """学校活动管理"""
    __tablename__ = "activities"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    activity_type = db.Column(db.String(30), default="其他")        # 运动会/艺术节/社会实践/社团活动/志愿服务/其他
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(100), default="")
    grade_id = db.Column(db.Integer, nullable=True)                  # NULL=全校
    target_classes = db.Column(db.Text, default="[]")                # JSON class_id 列表
    max_participants = db.Column(db.Integer, default=0)              # 0=不限
    organizer = db.Column(db.String(50), default="")
    cover_image = db.Column(db.String(200), default="")
    status = db.Column(db.String(20), default="draft")               # draft/published/ongoing/completed/cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship("User", foreign_keys=[created_by_id], lazy="joined")
    registrations = db.relationship("ActivityRegistration", backref="activity", lazy="dynamic",
                                    cascade="all, delete-orphan")


class ActivityRegistration(db.Model):
    """活动报名记录"""
    __tablename__ = "activity_registrations"
    __table_args__ = (
        db.UniqueConstraint("activity_id", "student_id", name="uq_activity_registration"),
    )
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="registered")          # registered/confirmed/cancelled
    note = db.Column(db.Text, default="")
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", lazy="joined")


class ActivitySignin(db.Model):
    """活动签到记录"""
    __tablename__ = "activity_signins"
    __table_args__ = (
        db.UniqueConstraint("activity_id", "student_id", name="uq_activity_signin"),
    )
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    signin_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="on_time")             # on_time/late/absent
    note = db.Column(db.Text, default="")

    student = db.relationship("Student", lazy="joined")


class MessageTemplate(db.Model):
    """消息模板"""
    __tablename__ = "message_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(30), default="通用")              # 违纪通知/成绩通知/家长会/活动通知/请假通知/表扬/通用
    title_template = db.Column(db.String(200), nullable=False)
    content_template = db.Column(db.Text, nullable=False)
    target_role = db.Column(db.String(30), nullable=True)            # 目标角色
    is_system = db.Column(db.Boolean, default=False)                 # 系统预设模板
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    use_count = db.Column(db.Integer, default=0)                     # 使用次数统计
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ══════════════════════════════════════════════════════════════
#  Block 4 新增模型 — 参数配置 / 报表 / 归档 / 消息互动
# ══════════════════════════════════════════════════════════════

class Semester(db.Model):
    """学期配置"""
    __tablename__ = "semesters"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)         # 2025-2026-1
    display_name = db.Column(db.String(40), nullable=False)              # 2025-2026学年第一学期
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SystemConfig(db.Model):
    """系统参数配置"""
    __tablename__ = "system_configs"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True)         # 配置键名
    value = db.Column(db.Text, default="")                               # 配置值
    category = db.Column(db.String(30), default="通用")                  # 分类
    description = db.Column(db.String(200), default="")                  # 说明
    updated_by = db.Column(db.String(64), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Report(db.Model):
    """系统报表"""
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(30), nullable=False)               # weekly/monthly/semester/custom
    title = db.Column(db.String(200), nullable=False)
    semester = db.Column(db.String(20), nullable=True)
    grade_id = db.Column(db.Integer, nullable=True)                      # NULL=全校
    class_id = db.Column(db.Integer, nullable=True)                      # NULL=全年级
    config_json = db.Column(db.Text, default="{}")                       # 生成参数 JSON
    data_json = db.Column(db.Text, default="{}")                         # 报表数据 JSON
    file_path = db.Column(db.String(300), nullable=True)                 # Excel/PDF 文件路径
    generated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)


class SemesterArchive(db.Model):
    """学期归档"""
    __tablename__ = "semester_archives"
    id = db.Column(db.Integer, primary_key=True)
    semester_name = db.Column(db.String(20), nullable=False)             # 2025-2026-1
    display_name = db.Column(db.String(40), default="")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    summary_json = db.Column(db.Text, default="{}")                      # 汇总数据 JSON
    archived_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    archived_at = db.Column(db.DateTime, default=datetime.utcnow)


class MessageReply(db.Model):
    """消息回复"""
    __tablename__ = "message_replies"
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    message = db.relationship("Message", backref=db.backref("replies", lazy="dynamic", cascade="all, delete-orphan"), lazy="joined")
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")


class MessageRead(db.Model):
    """消息已读跟踪"""
    __tablename__ = "message_reads"
    __table_args__ = (
        db.UniqueConstraint("message_id", "user_id", name="uq_message_read"),
    )
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── 心理健康评估 ──
class MentalHealthAssessment(db.Model):
    """心理健康评估记录"""
    __tablename__ = "mental_health_assessments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)

    # 评估类型: questionnaire(问卷), interview(访谈), observation(观察), parent_feedback(家长反馈)
    assessment_type = db.Column(db.String(30), nullable=False, default="questionnaire")

    # 评估日期
    assessment_date = db.Column(db.Date, default=date.today, index=True)

    # 量表名称（如：PHQ-9, GAD-7, SCL-90, 自定义）
    scale_name = db.Column(db.String(100), nullable=True)

    # 总分
    total_score = db.Column(db.Integer, nullable=True)

    # 风险等级: low(低风险), medium(中风险), high(高风险)
    risk_level = db.Column(db.String(20), default="low", index=True)

    # 详细得分（JSON格式，存储各维度分数）
    dimension_scores = db.Column(db.Text, nullable=True)

    # 评估结论
    conclusion = db.Column(db.Text, nullable=True)

    # 建议措施
    recommendations = db.Column(db.Text, nullable=True)

    # 是否需要干预: 0=否, 1=是
    need_intervention = db.Column(db.Boolean, default=False)

    # 干预措施
    intervention_plan = db.Column(db.Text, nullable=True)

    # 评估人
    assessed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # 审核状态: draft(草稿), reviewed(已审核), archived(已归档)
    status = db.Column(db.String(20), default="draft")

    # 审核人
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    student = db.relationship("Student", foreign_keys=[student_id], lazy="joined")
    assessor = db.relationship("User", foreign_keys=[assessed_by], lazy="joined")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by], lazy="joined")


# ── 心理健康评估问题库 ──
class MentalHealthQuestion(db.Model):
    """心理健康评估问题库"""
    __tablename__ = "mental_health_questions"

    id = db.Column(db.Integer, primary_key=True)
    # 量表名称
    scale_name = db.Column(db.String(100), nullable=False, index=True)
    # 维度（如：抑郁、焦虑、强迫、人际敏感等）
    dimension = db.Column(db.String(50), nullable=False)
    # 题号
    question_no = db.Column(db.Integer, nullable=False)
    # 题目内容
    question_text = db.Column(db.Text, nullable=False)
    # 选项类型: 4point(4级评分), 5point(5级评分), yes_no(是否), text(文字)
    option_type = db.Column(db.String(20), default="4point")
    # 是否反向计分: 0=否, 1=是
    reverse_scoring = db.Column(db.Boolean, default=False)
    # 排序
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("scale_name", "dimension", "question_no", name="uq_mh_question"),
    )


# ── 心理健康评估答案 ──
class MentalHealthAnswer(db.Model):
    """心理健康评估答案记录"""
    __tablename__ = "mental_health_answers"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("mental_health_assessments.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("mental_health_questions.id"), nullable=False)
    # 答案值（根据option_type不同：1-4, 1-5, 0/1, 或文字）
    answer_value = db.Column(db.Integer, nullable=True)
    answer_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "question_id", name="uq_mh_answer"),
    )

    question = db.relationship("MentalHealthQuestion", backref=db.backref("answers", lazy="selectin"), lazy="joined")
    assessment = db.relationship("MentalHealthAssessment", backref=db.backref("answers", lazy="selectin", cascade="all, delete-orphan"), lazy="joined")


# ── AI风险预警扫描记录 ──
class RiskRecord(db.Model):
    """AI预警扫描记录 — 每次定时/手动扫描的结果存档"""
    __tablename__ = "risk_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)

    # 扫描日期
    scan_date = db.Column(db.Date, default=date.today, index=True)

    # 风险等级: red(高风险), yellow(中风险), green(低风险)
    risk_level = db.Column(db.String(20), default="green", index=True)

    # 触发的预警项（JSON数组，每项包含 type/level/text/suggestion）
    warning_details = db.Column(db.Text, nullable=True)

    # 预警项数量
    warning_count = db.Column(db.Integer, default=0)

    # XGBoost 预测概率（None 表示未运行模型预测）
    risk_probability = db.Column(db.Float, nullable=True)

    # 特征归因（JSON对象，包含 top_triggers + feature_contributions）
    # 示例: {"top_triggers": [...], "contributions": {...}, "summary": "..."}
    feature_attribution = db.Column(db.Text, nullable=True)

    # 是否已发送通知
    notification_sent = db.Column(db.Boolean, default=False)

    # 是否已被查看/处理
    is_processed = db.Column(db.Boolean, default=False)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    process_note = db.Column(db.Text, nullable=True)
    # 处置类型: talk(谈话)/home_visit(家访)/notify_parent(通知家长)/monitor(持续观察)/resolved(已解决)
    disposal_action = db.Column(db.String(30), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    student = db.relationship("Student", foreign_keys=[student_id], lazy="joined")
    processor = db.relationship("User", foreign_keys=[processed_by], lazy="joined")

    def to_dict(self):
        """安全 JSON 序列化 — 不含关系对象，datetime/date 转为 isoformat"""
        ws = []
        if self.warning_details:
            try:
                ws = json.loads(self.warning_details) if isinstance(self.warning_details, str) else self.warning_details
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student_name": self.student.name if self.student else "",
            "grade_id": self.grade_id,
            "class_id": self.class_id,
            "scan_date": self.scan_date.isoformat() if self.scan_date else None,
            "risk_level": self.risk_level,
            "warning_details": ws,
            "warning_count": self.warning_count or 0,
            "risk_probability": self.risk_probability,
            "feature_attribution": self.feature_attribution,
            "notification_sent": self.notification_sent,
            "is_processed": self.is_processed,
            "processed_by": self.processed_by,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "process_note": self.process_note or "",
            "disposal_action": self.disposal_action or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 联动幂等性日志（防重入） ──
class LinkageLog(db.Model):
    """联动操作幂等性登记表

    每条联动写入前，先尝试 insert 此表。唯一键保证同一联动只执行一次。

    linkage_type 枚举：
      discipline_to_quality  — 违纪→扣素质分
      discipline_escalation  — 违纪→自动升级
      survey_to_assessment   — 问卷→心理评估
      score_to_risk          — 成绩→AI风险分析
      score_to_notify_parent — 成绩→通知家长
      attendance_to_notify   — 考勤→通知
      leave_to_notify        — 请假→通知
      appeal_to_notify       — 申诉→通知
      notice_to_notify       — 公告→通知
      meeting_to_notify      — 家长会→通知
      activity_to_notify     — 活动→通知
    """
    __tablename__ = "linkage_logs"
    __table_args__ = (
        UniqueConstraint("linkage_type", "source_key", "target_key",
                         name="uq_linkage_source_target"),
    )

    id = db.Column(db.Integer, primary_key=True)
    linkage_type = db.Column(db.String(40), nullable=False, index=True)
    source_key = db.Column(db.String(120), nullable=False, comment="来源唯一标识，如 'discipline:42'")
    target_key = db.Column(db.String(120), nullable=False, comment="目标唯一标识，如 'quality:15:s1'")
    extra_info = db.Column(db.Text, nullable=True, comment="补充信息JSON")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ── 班主任手记（学生主观备注） ──
class TeacherNote(db.Model):
    """班主任对学生的主观观察记录，保留人工判断的定性空间"""
    __tablename__ = "teacher_notes"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), default="observation")    # observation/talk/intervention/positive/concern
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("teacher_notes", lazy="selectin"), lazy="joined")
    teacher = db.relationship("User", foreign_keys=[teacher_id], lazy="joined")


# ═════════════════════════════════════════════════════════════
#  Block 5 — 教学干预效果闭环 (Phase 5.3 方案A)
# ═════════════════════════════════════════════════════════════

class InterventionRecord(db.Model):
    """
    教学干预记录 — 追踪 AI 预测 → 干预措施 → 后验效果 的完整闭环。

    核心字段:
      risk_before:  干预前 AI 风险概率 (snapshot)
      risk_after:   干预后 AI 风险概率 (随访时填入)
      intervention_type: 谈话/家长联动/座位调整/学业辅导/其他
      effect_rating: 显著改善/略有改善/无变化/恶化
      follow_up_done: 随访是否完成

    后验分析:
      risk_delta   = risk_before - risk_after   (正值=风险下降)
      slope        = risk_delta / days_between  (风险下滑斜率)
    """
    __tablename__ = "intervention_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # 风险概率快照
    risk_before = db.Column(db.Float, nullable=True)   # 干预前风险概率 [0,1]
    risk_after  = db.Column(db.Float, nullable=True)   # 干预后风险概率 (随访时填)

    # 干预措施
    intervention_type = db.Column(db.String(50), nullable=False, index=True)
    # 枚举值: 谈话/家长联动/座位调整/学业辅导/心理干预/行为契约/其他

    # 闭环状态 — tracking(追踪中,等待后续 predict 自动刷新 risk_after) / completed(已结案)
    status = db.Column(db.String(20), default="tracking", nullable=False, index=True)

    notes = db.Column(db.Text, nullable=True)           # 谈话记录 / 干预详情

    # 效果自评 (随访时填)
    effect_rating = db.Column(db.String(20), nullable=True, index=True)
    # 枚举值: 显著改善/略有改善/无变化/恶化

    # 时间线
    intervention_date = db.Column(db.Date, default=date.today, index=True)
    follow_up_date    = db.Column(db.Date, nullable=True)   # 计划随访日期
    follow_up_done    = db.Column(db.Boolean, default=False)  # 随访是否完成
    follow_up_notes  = db.Column(db.Text, nullable=True)    # 随访记录

    created_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── 关系 ──
    student = db.relationship("Student", foreign_keys=[student_id],
                              backref=db.backref("interventions", lazy="selectin",
                                                 cascade="all, delete-orphan"), lazy="joined")
    teacher = db.relationship("User", foreign_keys=[teacher_id],
                              backref=db.backref("interventions_created", lazy="dynamic"), lazy="joined")

    @property
    def risk_delta(self):
        """风险概率变化值 (正值 = 风险下降，是好事)"""
        if self.risk_before is None or self.risk_after is None:
            return None
        return round(self.risk_before - self.risk_after, 4)

    @property
    def days_between(self):
        """干预到随访的天数"""
        if not self.follow_up_date or not self.intervention_date:
            return None
        return (self.follow_up_date - self.intervention_date).days

    @property
    def risk_slope(self):
        """风险下滑斜率 = delta / days (越大越好)"""
        d = self.risk_delta
        days = self.days_between
        if d is None or days is None or days == 0:
            return None
        return round(d / days, 4)

    @property
    def is_effective(self):
        """是否干预有效 (显著改善 或 略有改善)"""
        return self.effect_rating in ("显著改善", "略有改善")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student_name": self.student.name if self.student else "",
            "teacher_id": self.teacher_id,
            "teacher_name": self.teacher.display_name if self.teacher else "",
            "risk_before": self.risk_before,
            "risk_after": self.risk_after,
            "risk_delta": self.risk_delta,
            "risk_slope": self.risk_slope,
            "intervention_type": self.intervention_type,
            "effect_rating": self.effect_rating,
            "is_effective": self.is_effective,
            "intervention_date": self.intervention_date.isoformat() if self.intervention_date else None,
            "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None,
            "follow_up_done": self.follow_up_done,
            "status": self.status,
            "notes_snippet": (self.notes or "")[:80],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
