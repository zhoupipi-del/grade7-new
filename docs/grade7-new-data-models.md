# 梨江中学德育管理平台 (grade7-new) — 数据库模型文档

> 版本: 1.0 | 最后更新: 2026-06-07 | 42 张数据表

---

## 模型总览

| # | 模型类 | 表名 | 说明 |
|---|--------|------|------|
| 1 | User | users | 用户账号 |
| 2 | Grade | grades | 年级 |
| 3 | Class | classes | 班级 |
| 4 | Student | students | 学生信息 |
| 5 | Subject | subjects | 考试科目 |
| 6 | Semester | semesters | 学期 |
| 7 | Exam | exams | 考试 |
| 8 | Score | scores | 考试成绩 |
| 9 | Attendance | attendance | 考勤记录 |
| 10 | LeaveRequest | leave_requests | 请假申请 |
| 11 | DisciplineRecord | discipline_records | 违纪记录 |
| 12 | DisciplineAppeal | discipline_appeals | 违纪申诉 |
| 13 | RoutineScore | routine_scores | 常规评分 |
| 14 | Task | tasks | 德育任务 |
| 15 | TaskFeedback | task_feedbacks | 任务反馈 |
| 16 | Message | messages | 站内消息 |
| 17 | MessageReply | message_replies | 消息回复 |
| 18 | MessageRead | message_reads | 消息已读 |
| 19 | Announcement | announcements | 系统公告 |
| 20 | Notice | notices | 通知公告 |
| 21 | NoticeReceipt | notice_receipts | 通知签收 |
| 22 | WingsScore | wings_scores | 五翼评价 |
| 23 | QualityIndicator | quality_indicators | 素质评价指标 |
| 24 | QualityScore | quality_scores | 素质评价得分 |
| 25 | Activity | activities | 活动 |
| 26 | ActivityRegistration | activity_registrations | 活动报名 |
| 27 | ActivitySignin | activity_signins | 活动签到 |
| 28 | ProblemStudent | problem_students | 问题学生 |
| 29 | ProblemTrack | problem_tracks | 问题跟踪 |
| 30 | EndTermComment | endterm_comments | 期末评语 |
| 31 | ParentMeeting | parent_meetings | 家长会 |
| 32 | ParentMeetingSignin | parent_meeting_signins | 家长会签到 |
| 33 | HomeVisit | home_visits | 家访记录 |
| 34 | PsychSurvey | psych_surveys | 心理问卷 |
| 35 | MentalHealthAssessment | mental_health_assessments | 心理健康评估 |
| 36 | MentalHealthQuestion | mental_health_questions | 心理测评题目 |
| 37 | MentalHealthAnswer | mental_health_answers | 心理测评答案 |
| 38 | MessageTemplate | message_templates | 消息模板 |
| 39 | SystemConfig | system_configs | 系统配置项 |
| 40 | AuditLog | audit_logs | 审计日志 |
| 41 | Report | reports | 报表 |
| 42 | SemesterArchive | semester_archives | 学期归档 |

---

## 一、核心基础表

### 1. User (users) — 用户账号

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL, INDEX | 登录名 |
| `password_hash` | VARCHAR(256) | NOT NULL | bcrypt 哈希 |
| `display_name` | VARCHAR(64) | NOT NULL | 显示名称 |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT "teacher", INDEX | 角色: ms_admin/grade_leader/class_teacher/teacher/parent/student |
| `grade_id` | INTEGER | NULL | 绑定年级 |
| `class_id` | INTEGER | NULL | 绑定班级 |
| `bound_student_id` | INTEGER | NULL | 家长绑定的孩子 |
| `phone` | VARCHAR(20) | NULL | 手机号 |
| `is_active` | BOOLEAN | DEFAULT TRUE | 是否启用 |
| `created_at` | DATETIME | — | 创建时间 |
| `last_login` | DATETIME | NULL | 最后登录时间 |

### 2. Grade (grades) — 年级

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(64) | UNIQUE, NOT NULL | 年级名称 (如 "七年级") |
| `sort_order` | INTEGER | DEFAULT 0 | 排序 |
| `is_active` | BOOLEAN | DEFAULT TRUE | 是否启用 (软删除) |

### 3. Class (classes) — 班级

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(64) | NOT NULL | 班级名称 (如 "七(1)班") |
| `grade_id` | INTEGER | FK(grades.id), NOT NULL, INDEX | 所属年级 |
| `head_teacher_id` | INTEGER | FK(users.id), NULL | 班主任 |
| `student_count` | INTEGER | DEFAULT 0 | 学生数 |
| `is_active` | BOOLEAN | DEFAULT TRUE | 是否启用 |

### 4. Student (students) — 学生信息

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(64) | NOT NULL | 姓名 |
| `student_no` | VARCHAR(20) | UNIQUE, NOT NULL, INDEX | 学号 |
| `class_id` | INTEGER | FK(classes.id), NOT NULL, INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), NOT NULL, INDEX | 年级 |
| `gender` | VARCHAR(4) | DEFAULT "男" | 性别 |
| `id_card` | VARCHAR(18) | NULL | 身份证号 |
| `national_id` | VARCHAR(20) | NULL | 全国学籍号 |
| `ethnicity` | VARCHAR(20) | DEFAULT "汉族" | 民族 |
| `birth_date` | DATE | NULL | 出生日期 |
| `address` | VARCHAR(200) | NULL | 家庭地址 |
| `parent1_name` | VARCHAR(64) | NULL | 家长1姓名 |
| `parent1_phone` | VARCHAR(20) | NULL | 家长1电话 |
| `parent1_relation` | VARCHAR(20) | NULL | 家长1关系 |
| `parent2_name` | VARCHAR(64) | NULL | 家长2姓名 |
| `parent2_phone` | VARCHAR(20) | NULL | 家长2电话 |
| `parent2_relation` | VARCHAR(20) | NULL | 家长2关系 |
| `primary_school` | VARCHAR(100) | NULL | 毕业小学 |
| `is_active` | BOOLEAN | DEFAULT TRUE | 是否在籍 |
| `enrolled_at` | DATE | NULL | 入学日期 |
| `tags` | TEXT | DEFAULT "" | 逗号分隔标签 |
| `created_at` | DATETIME | — | 创建时间 |

### 5. Subject (subjects) — 考试科目

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(20) | UNIQUE | 科目名 (语/数/英/...) |
| `full_score` | FLOAT | DEFAULT 100 | 满分 |
| `pass_score` | FLOAT | DEFAULT 60 | 及格线 |
| `sort_order` | INTEGER | DEFAULT 0 | 排序 |

### 6. Semester (semesters) — 学期

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(20) | UNIQUE | 学期标识 (如 "2025-1") |
| `display_name` | VARCHAR(40) | — | 显示名 (如 "2025年上学期") |
| `start_date` | DATE | — | 开始日期 |
| `end_date` | DATE | — | 结束日期 |
| `is_current` | BOOLEAN | — | 是否当前学期 |
| `created_at` | DATETIME | — | 创建时间 |

---

## 二、成绩相关

### 7. Exam (exams) — 考试

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(50) | UNIQUE | 考试名 (如 "七年级期中") |
| `exam_date` | DATE | — | 考试日期 |
| `exam_type` | VARCHAR(20) | — | 类型: 月考/期中/期末/模拟 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `created_at` | DATETIME | — | 创建时间 |

### 8. Score (scores) — 考试成绩

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `exam_id` | INTEGER | FK(exams.id) | 考试 |
| `subject_id` | INTEGER | FK(subjects.id) | 科目 |
| `class_id` | INTEGER | — | 冗余班级 |
| `grade_id` | INTEGER | — | 冗余年级 |
| `score` | FLOAT | DEFAULT 0 | 分数 |
| `rank_class` | INTEGER | DEFAULT 0 | 班级排名 |
| `rank_grade` | INTEGER | DEFAULT 0 | 年级排名 |

> 唯一约束: (student_id, exam_id, subject_id)

---

## 三、考勤与请假

### 9. Attendance (attendance) — 考勤记录

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | FK(classes.id), INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `status` | VARCHAR(20) | — | 状态: present/late/early/absent/leave |
| `record_date` | DATE | INDEX | 日期 |
| `note` | VARCHAR(200) | — | 备注 |
| `created_at` | DATETIME | — | 创建时间 |

### 10. LeaveRequest (leave_requests) — 请假申请

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id) | 学生 |
| `class_id` | INTEGER | FK(classes.id) | 班级 |
| `grade_id` | INTEGER | FK(grades.id) | 年级 |
| `applicant_id` | INTEGER | FK(users.id) | 申请人 |
| `reason` | TEXT | — | 请假原因 |
| `start_date` | DATE | — | 开始日期 |
| `end_date` | DATE | — | 结束日期 |
| `status` | VARCHAR(20) | DEFAULT "pending" | pending/class_approved/grade_approved/rejected |
| `class_approved_by` | INTEGER | NULL | 班主任审批人 |
| `class_approved_at` | DATETIME | NULL | 班主任审批时间 |
| `grade_approved_by` | INTEGER | NULL | 年级组长审批人 |
| `grade_approved_at` | DATETIME | NULL | 年级组长审批时间 |
| `created_at` | DATETIME | — | 创建时间 |

---

## 四、纪律管理

### 11. DisciplineRecord (discipline_records) — 违纪记录

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | FK(classes.id), INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `type` | VARCHAR(20) | — | 类型: warning/minor/major/serious |
| `category` | VARCHAR(40) | — | 违纪类别 |
| `description` | TEXT | — | 违纪描述 |
| `action_taken` | TEXT | — | 处理措施 |
| `points` | INTEGER | DEFAULT 0 | 扣分 |
| `status` | VARCHAR(20) | DEFAULT "active" | active/resolved |
| `created_by` | INTEGER | FK(users.id) | 记录人 |
| `created_at` | DATETIME | — | 创建时间 |
| `resolved_at` | DATETIME | NULL | 解决时间 |

### 12. DisciplineAppeal (discipline_appeals) — 违纪申诉

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `discipline_id` | INTEGER | FK(discipline_records.id), INDEX | 违纪记录 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | FK(classes.id) | 班级 |
| `grade_id` | INTEGER | FK(grades.id) | 年级 |
| `applicant_id` | INTEGER | FK(users.id) | 申诉人 |
| `reason` | TEXT | — | 申诉理由 |
| `status` | VARCHAR(20) | DEFAULT "pending" | pending/approved/rejected |
| `review_comment` | TEXT | — | 复核意见 |
| `reviewed_by` | INTEGER | FK(users.id), NULL | 复核人 |
| `reviewed_at` | DATETIME | NULL | 复核时间 |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

---

## 五、任务与消息

### 13. Task (tasks) — 德育任务

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `title` | VARCHAR(200) | NOT NULL | 任务标题 |
| `content` | TEXT | NOT NULL | 任务内容 |
| `from_role` | VARCHAR(20) | — | 发起角色 |
| `from_user_id` | INTEGER | FK(users.id) | 发起人 |
| `target_type` | VARCHAR(20) | — | 目标类型: grade/class/student |
| `target_id` | INTEGER | — | 目标ID |
| `status` | VARCHAR(20) | DEFAULT "pending" | pending/doing/done/closed |
| `deadline` | DATE | NULL | 截止日期 |
| `created_at` | DATETIME | — | 创建时间 |
| `finished_at` | DATETIME | NULL | 完成时间 |

### 14. TaskFeedback (task_feedbacks) — 任务反馈

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `task_id` | INTEGER | FK(tasks.id) | 任务 |
| `user_id` | INTEGER | FK(users.id) | 反馈人 |
| `content` | TEXT | — | 反馈内容 |
| `created_at` | DATETIME | — | 创建时间 |

### 15. Message (messages) — 站内消息

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `from_user_id` | INTEGER | FK(users.id), NULL | 发送者(NULL=系统) |
| `to_user_id` | INTEGER | FK(users.id), INDEX | 接收者 |
| `title` | VARCHAR(200) | — | 标题 |
| `content` | TEXT | — | 内容 |
| `category` | VARCHAR(30) | — | 分类: 通用/违纪通知/成绩通知/请假通知/任务通知 |
| `is_read` | BOOLEAN | DEFAULT FALSE | 是否已读 |
| `created_at` | DATETIME | — | 创建时间 |

### 16. MessageReply (message_replies) — 消息回复

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `message_id` | INTEGER | FK(messages.id), INDEX | 消息 |
| `user_id` | INTEGER | FK(users.id) | 回复人 |
| `content` | TEXT | — | 回复内容 |
| `created_at` | DATETIME | — | 创建时间 |

### 17. MessageRead (message_reads) — 消息已读记录

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `message_id` | INTEGER | FK(messages.id), INDEX | 消息 |
| `user_id` | INTEGER | FK(users.id) | 用户 |
| `read_at` | DATETIME | — | 已读时间 |

> 唯一约束: (message_id, user_id)

### 18. Announcement (announcements) — 系统公告

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `title` | VARCHAR(200) | — | 标题 |
| `content` | TEXT | — | 内容 |
| `author` | VARCHAR(64) | — | 发布人 |
| `is_pinned` | BOOLEAN | — | 是否置顶 |
| `is_active` | BOOLEAN | — | 是否启用 |
| `target_roles` | VARCHAR(200) | — | 目标角色 (逗号分隔) |
| `expire_date` | DATE | NULL | 过期日期 |
| `created_at` | DATETIME | — | 创建时间 |

---

## 六、通知公告

### 19. Notice (notices) — 通知公告

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `title` | VARCHAR(200) | NOT NULL | 标题 |
| `content` | TEXT | NOT NULL | 内容 |
| `class_id` | INTEGER | FK(classes.id), NULL | 目标班级(NULL=全年级) |
| `grade_id` | INTEGER | — | 年级 |
| `require_receipt` | BOOLEAN | — | 是否需要签收 |
| `created_by` | VARCHAR(50) | — | 创建人姓名 |
| `created_by_id` | INTEGER | FK(users.id) | 创建人ID |
| `created_at` | DATETIME | — | 创建时间 |

### 20. NoticeReceipt (notice_receipts) — 通知签收

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `notice_id` | INTEGER | FK(notices.id), INDEX | 通知 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生(家长签收) |
| `status` | VARCHAR(10) | DEFAULT "unread" | unread/read/signed |
| `read_at` | DATETIME | NULL | 阅读时间 |
| `signed_at` | DATETIME | NULL | 签名时间 |
| `signed_by` | VARCHAR(30) | NULL | 签名者 |

> 唯一约束: (notice_id, student_id)

---

## 七、评价系统

### 21. RoutineScore (routine_scores) — 常规评分

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `class_id` | INTEGER | FK(classes.id), INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `category` | VARCHAR(40) | — | 评分类别 (卫生/纪律/两操/礼仪) |
| `score` | INTEGER | — | 分数 |
| `note` | TEXT | — | 备注 |
| `inspector` | VARCHAR(64) | — | 检查人 |
| `record_date` | DATE | INDEX | 日期 |
| `created_at` | DATETIME | — | 创建时间 |

### 22. WingsScore (wings_scores) — 五翼评价

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `grade_id` | INTEGER | — | 年级 |
| `dimension` | VARCHAR(40) | — | 维度: 德/智/体/美/劳 |
| `score` | FLOAT | — | 得分 |
| `scorer_type` | VARCHAR(20) | — | 评分者类型: teacher/parent/self/peer |
| `scorer_id` | INTEGER | — | 评分者ID |
| `semester` | VARCHAR(20) | — | 学期 |
| `created_at` | DATETIME | — | 创建时间 |

### 23. QualityIndicator (quality_indicators) — 素质评价指标

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(50) | — | 指标名称 |
| `parent_id` | INTEGER | DEFAULT 0 | 父指标ID(0=一级) |
| `dimension` | VARCHAR(30) | — | 维度: moral/academic/health/art/social |
| `weight` | FLOAT | — | 权重 |
| `max_score` | FLOAT | DEFAULT 100 | 满分 |
| `sort_order` | INTEGER | — | 排序 |
| `is_active` | BOOLEAN | — | 是否启用 |

### 24. QualityScore (quality_scores) — 素质评价得分

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `grade_id` | INTEGER | — | 年级 |
| `indicator_id` | INTEGER | FK(quality_indicators.id) | 指标 |
| `score` | FLOAT | — | 得分 |
| `scorer_type` | VARCHAR(20) | — | self/peer/teacher/parent |
| `scorer_id` | INTEGER | — | 评分者ID |
| `semester` | VARCHAR(20) | — | 学期 |
| `comment` | TEXT | NULL | 评语 |
| `created_at` | DATETIME | — | 创建时间 |

---

## 八、活动管理

### 25. Activity (activities) — 活动

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `title` | VARCHAR(200) | — | 活动标题 |
| `description` | TEXT | — | 活动描述 |
| `activity_type` | VARCHAR(30) | — | 类型 |
| `start_date` | DATE | — | 开始日期 |
| `end_date` | DATE | — | 结束日期 |
| `location` | VARCHAR(100) | — | 地点 |
| `grade_id` | INTEGER | NULL | 年级 |
| `target_classes` | TEXT | NULL | 目标班级 (JSON数组) |
| `max_participants` | INTEGER | NULL | 最大参与人数 |
| `organizer` | VARCHAR(50) | — | 组织者 |
| `cover_image` | VARCHAR(200) | NULL | 封面图 |
| `status` | VARCHAR(20) | DEFAULT "draft" | draft/published/ongoing/completed/cancelled |
| `created_by_id` | INTEGER | FK(users.id) | 创建人 |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 26. ActivityRegistration (activity_registrations) — 活动报名

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `activity_id` | INTEGER | FK(activities.id), INDEX | 活动 |
| `student_id` | INTEGER | FK(students.id) | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `status` | VARCHAR(20) | DEFAULT "registered" | registered/confirmed/cancelled |
| `note` | TEXT | NULL | 备注 |
| `registered_at` | DATETIME | — | 报名时间 |

> 唯一约束: (activity_id, student_id)

### 27. ActivitySignin (activity_signins) — 活动签到

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `activity_id` | INTEGER | FK(activities.id), INDEX | 活动 |
| `student_id` | INTEGER | FK(students.id) | 学生 |
| `signin_time` | DATETIME | — | 签到时间 |
| `status` | VARCHAR(20) | DEFAULT "on_time" | on_time/late/absent |
| `note` | TEXT | NULL | 备注 |

> 唯一约束: (activity_id, student_id)

---

## 九、问题学生与心理健康

### 28. ProblemStudent (problem_students) — 问题学生档案

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | FK(classes.id), INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `category` | VARCHAR(40) | — | 类别: 心理/家庭/行为/学习/身体/混合 |
| `level` | VARCHAR(10) | — | 等级: red/yellow |
| `description` | TEXT | — | 问题描述 |
| `intervention` | TEXT | — | 干预措施 |
| `status` | VARCHAR(20) | DEFAULT "active" | active/monitoring/resolved |
| `created_by` | INTEGER | FK(users.id) | 建档人 |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 29. ProblemTrack (problem_tracks) — 问题跟踪记录

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `problem_id` | INTEGER | FK(problem_students.id) | 问题学生 |
| `content` | TEXT | — | 跟踪内容 |
| `created_by` | INTEGER | FK(users.id) | 记录人 |
| `created_at` | DATETIME | — | 创建时间 |

### 30. MentalHealthAssessment (mental_health_assessments) — 心理健康评估

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | FK(classes.id), INDEX | 班级 |
| `grade_id` | INTEGER | FK(grades.id), INDEX | 年级 |
| `assessment_type` | VARCHAR(30) | — | questionnaire/interview/observation/parent_feedback |
| `assessment_date` | DATE | INDEX | 评估日期 |
| `scale_name` | VARCHAR(100) | — | 量表名称 (如 MSSMHS-55) |
| `total_score` | INTEGER | — | 总分 |
| `risk_level` | VARCHAR(20) | INDEX | low/medium/high |
| `dimension_scores` | TEXT | — | 维度得分 (JSON) |
| `conclusion` | TEXT | — | 结论 |
| `recommendations` | TEXT | — | 建议 |
| `need_intervention` | BOOLEAN | — | 是否需要干预 |
| `intervention_plan` | TEXT | NULL | 干预方案 |
| `assessed_by` | INTEGER | FK(users.id) | 评估人 |
| `status` | VARCHAR(20) | DEFAULT "draft" | draft/reviewed/archived |
| `reviewed_by` | INTEGER | FK(users.id), NULL | 审核人 |
| `reviewed_at` | DATETIME | NULL | 审核时间 |
| `review_comment` | TEXT | NULL | 审核意见 |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 31. MentalHealthQuestion (mental_health_questions) — 测评题目

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `scale_name` | VARCHAR(100) | INDEX | 量表名 |
| `dimension` | VARCHAR(50) | — | 维度 |
| `question_no` | INTEGER | — | 题号 |
| `question_text` | TEXT | — | 题目内容 |
| `option_type` | VARCHAR(20) | — | 选项类型: 4point/5point/yes_no/text |
| `reverse_scoring` | BOOLEAN | — | 是否反向计分 |
| `sort_order` | INTEGER | — | 排序 |
| `is_active` | BOOLEAN | — | 是否启用 |
| `created_at` | DATETIME | — | 创建时间 |

> 唯一约束: (scale_name, dimension, question_no)

### 32. MentalHealthAnswer (mental_health_answers) — 测评答案

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `assessment_id` | INTEGER | FK(mental_health_assessments.id), INDEX | 评估 |
| `question_id` | INTEGER | FK(mental_health_questions.id) | 题目 |
| `answer_value` | INTEGER | NULL | 数值答案 |
| `answer_text` | TEXT | NULL | 文本答案 |
| `created_at` | DATETIME | — | 创建时间 |

> 唯一约束: (assessment_id, question_id)

### 33. PsychSurvey (psych_surveys) — 心理问卷

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `grade_id` | INTEGER | — | 年级 |
| `survey_type` | VARCHAR(40) | — | 问卷类型 |
| `answers_json` | TEXT | — | 答案 (JSON) |
| `total_score` | FLOAT | — | 总分 |
| `dimensions_json` | TEXT | — | 维度得分 (JSON) |
| `is_valid` | BOOLEAN | — | 是否有效 |
| `completed_at` | DATETIME | — | 完成时间 |

---

## 十、家长互动

### 34. EndTermComment (endterm_comments) — 期末评语

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `grade_id` | INTEGER | — | 年级 |
| `semester` | VARCHAR(20) | — | 学期 |
| `overall_comment` | TEXT | — | 综合评价 |
| `strengths` | TEXT | — | 优点 |
| `improvements` | TEXT | — | 待改进 |
| `teacher_suggestion` | TEXT | — | 教师建议 |
| `status` | VARCHAR(20) | DEFAULT "draft" | draft/published |
| `created_by` | VARCHAR(50) | — | 评语人姓名 |
| `created_by_id` | INTEGER | FK(users.id) | 评语人ID |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 35. ParentMeeting (parent_meetings) — 家长会

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `title` | VARCHAR(200) | — | 标题 |
| `meeting_date` | DATE | — | 日期 |
| `start_time` | VARCHAR(10) | — | 开始时间 |
| `end_time` | VARCHAR(10) | — | 结束时间 |
| `location` | VARCHAR(100) | — | 地点 |
| `grade_id` | INTEGER | FK(grades.id) | 年级 |
| `target_classes` | TEXT | — | 目标班级 (JSON数组) |
| `description` | TEXT | — | 说明 |
| `organizer` | VARCHAR(50) | — | 组织者 |
| `status` | VARCHAR(20) | DEFAULT "planned" | planned/ongoing/completed |
| `created_by` | VARCHAR(50) | — | 创建人 |
| `created_by_id` | INTEGER | FK(users.id) | 创建人ID |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 36. ParentMeetingSignin (parent_meeting_signins) — 家长会签到

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `meeting_id` | INTEGER | FK(parent_meetings.id), INDEX | 家长会 |
| `student_id` | INTEGER | FK(students.id) | 学生 |
| `parent_name` | VARCHAR(50) | — | 家长姓名 |
| `phone` | VARCHAR(20) | — | 手机号 |
| `is_late` | BOOLEAN | — | 是否迟到 |
| `notes` | TEXT | NULL | 备注 |
| `signin_time` | DATETIME | — | 签到时间 |

### 37. HomeVisit (home_visits) — 家访记录

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `student_id` | INTEGER | FK(students.id), INDEX | 学生 |
| `class_id` | INTEGER | — | 班级 |
| `grade_id` | INTEGER | — | 年级 |
| `visit_date` | DATE | — | 日期 |
| `visit_type` | VARCHAR(20) | — | 方式: 上门/电话/来校/线上/其他 |
| `content_summary` | TEXT | — | 内容摘要 |
| `parent_feedback` | TEXT | — | 家长反馈 |
| `teacher_name` | VARCHAR(50) | — | 教师姓名 |
| `follow_up` | TEXT | NULL | 后续跟进 |
| `created_by_id` | INTEGER | FK(users.id) | 创建人 |
| `created_at` | DATETIME | — | 创建时间 |

---

## 十一、系统管理

### 38. MessageTemplate (message_templates) — 消息模板

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `name` | VARCHAR(100) | UNIQUE | 模板名称 |
| `category` | VARCHAR(30) | — | 分类 |
| `title_template` | VARCHAR(200) | — | 标题模板 (支持变量) |
| `content_template` | TEXT | — | 内容模板 (支持变量) |
| `target_role` | VARCHAR(30) | — | 目标角色 |
| `is_system` | BOOLEAN | — | 是否系统内置 |
| `created_by_id` | INTEGER | FK(users.id) | 创建人 |
| `use_count` | INTEGER | DEFAULT 0 | 使用次数 |
| `created_at` | DATETIME | — | 创建时间 |
| `updated_at` | DATETIME | — | 更新时间 |

### 39. SystemConfig (system_configs) — 系统配置

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `key` | VARCHAR(100) | UNIQUE | 配置键 |
| `value` | TEXT | — | 配置值 |
| `category` | VARCHAR(30) | — | 分类 |
| `description` | VARCHAR(200) | — | 说明 |
| `updated_by` | VARCHAR(64) | — | 修改人 |
| `updated_at` | DATETIME | — | 修改时间 |

默认配置项: site_name, academic_year, score_entry_deadline, allow_modify_score, late_threshold, early_leave_threshold, notify_parent_auto, notify_teacher_on_discipline

### 40. AuditLog (audit_logs) — 审计日志

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `username` | VARCHAR(50) | — | 操作用户 |
| `action` | VARCHAR(50) | — | 操作: CREATE/UPDATE/DELETE |
| `target_type` | VARCHAR(30) | — | 目标类型 |
| `target_id` | INTEGER | — | 目标ID |
| `detail` | TEXT | — | 详情 |
| `created_at` | DATETIME | — | 创建时间 |

### 41. Report (reports) — 报表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `report_type` | VARCHAR(30) | — | 类型: weekly/monthly/semester/custom |
| `title` | VARCHAR(200) | — | 标题 |
| `semester` | VARCHAR(20) | — | 学期 |
| `grade_id` | INTEGER | NULL | 年级 |
| `class_id` | INTEGER | NULL | 班级 |
| `config_json` | TEXT | — | 配置 (JSON) |
| `data_json` | TEXT | — | 数据 (JSON) |
| `file_path` | VARCHAR(300) | NULL | 文件路径 |
| `generated_by_id` | INTEGER | FK(users.id) | 生成人 |
| `generated_at` | DATETIME | — | 生成时间 |

### 42. SemesterArchive (semester_archives) — 学期归档

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK | 主键 |
| `semester_name` | VARCHAR(20) | — | 学期标识 |
| `display_name` | VARCHAR(40) | — | 显示名 |
| `start_date` | DATE | — | 开始日期 |
| `end_date` | DATE | — | 结束日期 |
| `summary_json` | TEXT | — | 汇总数据 (JSON) |
| `archived_by_id` | INTEGER | FK(users.id) | 归档人 |
| `archived_at` | DATETIME | — | 归档时间 |

---

## 索引清单

### 高频查询索引

| 表 | 索引字段 | 说明 |
|----|----------|------|
| users | username | 登录查询 |
| users | role | 角色筛选 |
| students | student_no | 学号查询 |
| students | class_id, grade_id | 按班级/年级筛选 |
| attendance | record_date | 按日期查询 |
| attendance | student_id, class_id, grade_id | 多级筛选 |
| discipline_records | student_id, class_id, grade_id | 多级筛选 |
| discipline_appeals | discipline_id, student_id | 关联查询 |
| discipline_appeals | status | 状态筛选 |
| scores | student_id | 学生成绩 |
| notices | — | — |
| notice_receipts | notice_id, student_id | 签收查询 |
| leave_requests | status | 审批状态 |
| wings_scores | student_id | 五翼得分 |
| quality_scores | student_id | 素质得分 |
| mental_health_assessments | student_id, class_id, grade_id | 多级筛选 |
| mental_health_assessments | risk_level | 风险等级 |
| mental_health_assessments | assessment_date | 按日期查询 |
| mental_health_questions | scale_name | 量表查询 |
| mental_health_answers | assessment_id | 评估关联 |

---

*文档生成时间: 2026-06-07*
