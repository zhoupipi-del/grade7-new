# 梨江中学德育管理平台 (grade7-new) — API 路由文档

> 版本: 1.0 | 最后更新: 2026-06-07 | 31 蓝图 · ~250+ 路由

---

## 路由总览

| # | 蓝图 | URL 前缀 | 路由数 | 权限要求 |
|---|------|----------|--------|----------|
| 1 | auth | `/` | 7 | 公开+管理员 |
| 2 | ms | `/ms` | 33 | ms_admin |
| 3 | grade | `/grade` | 12 | grade_leader |
| 4 | class_ | `/class` | 22 | class_teacher |
| 5 | parent_portal | `/parent` | 16 | parent |
| 6 | common | `/common` | 9 | 登录用户 |
| 7 | api_miniapp | `/api/v1` | 22 | JWT Token |
| 8 | wings | `/wings` | 11 | 多角色 |
| 9 | quality | `/quality` | 13 | 多角色 |
| 10 | activity | `/activity` | 20 | 多角色 |
| 11 | scores | `/scores` | 16 | 多角色 |
| 12 | notices | `/notices` | 7 | 多角色 |
| 13 | system_config | `/system` | 10 | ms_admin |
| 14 | semester_archive | `/archive` | 8 | ms_admin |
| 15 | report_generator | `/reports` | 5 | ms_admin |
| 16 | endterm_comment | `/endterm-comment` | 6 | class_teacher |
| 17 | parent_meeting | `/parent-meeting` | 6 | 多角色 |
| 18 | mental_health | `/mental-health` | 6 | 多角色 |
| 19 | survey | `/survey` | 6 | 多角色 |
| 20 | message_templates | `/message-templates` | 5 | ms_admin |
| 21 | backup | `/backup` | 5 | ms_admin |
| 22 | home_visit | `/home-visits` | 4 | class_teacher |
| 23 | communication | `/communication` | 3 | class_teacher |
| 24 | attendance_stats | `/attendance-stats` | 5 | 多角色 |
| 25 | tags | `/tags` | 3 | 多角色 |
| 26 | workload | `/workload` | 3 | 多角色 |
| 27 | bigscreen | `/bigscreen` | 2 | ms_admin |
| 28 | ai_analysis | `/ai-analysis` | 2 | 多角色 |
| 29 | export_summary | `/export-summary` | 2 | ms_admin |
| 30 | audit | `/audit` | 1 | ms_admin |
| 31 | search | `/search` | 5 | 登录用户 |

---

## 一、auth — 认证模块（7 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET,POST | `/login` | `login_page()` | 登录页 |
| GET | `/logout` | `logout()` | 退出登录 |
| GET,POST | `/change-password` | `change_password()` | 修改密码 |
| GET | `/accounts` | `account_list()` | 账号列表 |
| GET,POST | `/accounts/create` | `create_account()` | 创建账号 |
| POST | `/accounts/<int:uid>/toggle` | `toggle_account(uid)` | 启用/停用账号 |
| POST | `/accounts/<int:uid>/reset-password` | `reset_password(uid)` | 重置密码 |

---

## 二、ms — 德育处工作台（33 路由）

### 工作台
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/` | `dashboard()` | 工作台首页（统计概览） |
| GET | `/ms/tasks` | `task_list()` | 任务列表 |
| POST | `/ms/tasks/create` | `create_task()` | 创建任务 |
| GET | `/ms/tasks/<int:tid>` | `task_detail(tid)` | 任务详情 |
| POST | `/ms/tasks/<int:tid>/close` | `close_task(tid)` | 关闭任务 |

### 纪律管理
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/discipline` | `discipline_list()` | 全校纪律记录 |
| POST | `/ms/discipline/add` | `add_discipline()` | 添加违纪 |
| POST | `/ms/discipline/<int:rid>/delete` | `delete_discipline(rid)` | 删除违纪 |
| GET | `/ms/discipline/stats` | `discipline_stats()` | 违纪统计 |
| POST | `/ms/discipline/<int:rid>/resolve` | `discipline_resolve(rid)` | 标记已解决 |
| GET | `/ms/appeals` | `appeal_list()` | 申诉列表 |
| GET,POST | `/ms/appeals/<int:aid>` | `appeal_review(aid)` | 申诉复核 |

### 常规评分
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/routine` | `routine_overview()` | 常规评分总览 |
| POST | `/ms/routine/add` | `add_routine()` | 添加评分 |
| POST | `/ms/routine/<int:sid>/delete` | `delete_routine(sid)` | 删除评分 |
| GET | `/ms/leaderboard` | `leaderboard()` | 流动红旗排名 |

### 问题学生
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/problem-students` | `problem_list()` | 问题学生列表 |
| GET,POST | `/ms/problem-students/create` | `create_problem()` | 创建问题学生 |
| GET | `/ms/problem-students/<int:pid>` | `problem_detail(pid)` | 问题学生详情 |
| POST | `/ms/problem-students/<int:pid>/track` | `add_track(pid)` | 添加跟踪记录 |

### 基础数据管理
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/grades` | `grade_manage()` | 年级列表 |
| GET,POST | `/ms/grades/create` | `grade_create()` | 创建年级 |
| GET,POST | `/ms/grades/<int:gid>/edit` | `grade_edit(gid)` | 编辑年级 |
| POST | `/ms/grades/<int:gid>/delete` | `grade_delete(gid)` | 删除年级 |
| GET | `/ms/classes` | `class_manage()` | 班级列表 |
| GET,POST | `/ms/classes/create` | `class_create()` | 创建班级 |
| GET,POST | `/ms/classes/<int:cid>/edit` | `class_edit(cid)` | 编辑班级 |
| POST | `/ms/classes/<int:cid>/delete` | `class_delete(cid)` | 删除班级 |
| GET | `/ms/subjects` | `subject_manage()` | 科目列表 |
| GET,POST | `/ms/subjects/create` | `subject_create()` | 创建科目 |
| GET,POST | `/ms/subjects/<int:sid>/edit` | `subject_edit(sid)` | 编辑科目 |
| POST | `/ms/subjects/<int:sid>/delete` | `subject_delete(sid)` | 删除科目 |

### 其他
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/ms/attendance` | `attendance_overview()` | 全校考勤总览(支持Excel导出) |
| GET | `/ms/api/students/search` | `search_students()` | 学生搜索API |

---

## 三、grade — 年级组工作台（12 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/grade/` | `dashboard()` | 年级组首页 |
| GET | `/grade/tasks` | `task_list()` | 年级任务列表 |
| POST | `/grade/tasks/assign` | `assign_task()` | 分配任务到班级 |
| GET | `/grade/tasks/<int:tid>/feedback` | `task_feedback(tid)` | 查看任务反馈 |
| GET | `/grade/discipline` | `discipline_list()` | 年级违纪记录 |
| POST | `/grade/discipline/add` | `add_discipline()` | 添加违纪 |
| POST | `/grade/discipline/<int:rid>/delete` | `delete_discipline(rid)` | 删除违纪 |
| POST | `/grade/discipline/<int:rid>/resolve` | `resolve_discipline(rid)` | 标记已解决 |
| GET | `/grade/routine` | `routine_overview()` | 年级常规评分 |
| POST | `/grade/routine/add` | `add_routine()` | 添加评分 |
| POST | `/grade/routine/<int:sid>/delete` | `delete_routine(sid)` | 删除评分 |
| GET | `/grade/attendance` | `attendance_overview()` | 年级考勤总览 |
| POST | `/grade/attendance/record` | `record_attendance()` | 录入考勤 |
| GET | `/grade/leaves` | `leave_list()` | 请假列表 |
| POST | `/grade/leaves/<int:lid>/approve` | `approve_leave(lid)` | 审批请假 |
| POST | `/grade/leaves/batch-approve` | `batch_approve_leaves()` | 批量审批请假 |
| GET | `/grade/problem-students` | `problem_list()` | 年级问题学生 |

---

## 四、class_ — 班主任工作台（22 路由）

### 学生管理
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/class/` | `dashboard()` | 班主任首页 |
| GET | `/class/students` | `student_list()` | 学生花名册 |
| GET,POST | `/class/students/add` | `add_student()` | 添加学生 |
| GET,POST | `/class/students/<int:sid>/edit` | `edit_student(sid)` | 编辑学生 |
| POST | `/class/students/<int:sid>/delete` | `delete_student(sid)` | 删除学生 |
| POST | `/class/students/import` | `import_students()` | Excel批量导入 |
| GET | `/class/students/template` | `download_template()` | 下载导入模板 |
| GET | `/class/students/export` | `export_students()` | 导出本班Excel |
| GET | `/class/students/<int:sid>` | `student_detail(sid)` | 学生详情 |

### 纪律管理
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/class/discipline` | `discipline_list()` | 纪律记录列表 |
| POST | `/class/discipline/add` | `add_discipline()` | 添加违纪 |
| GET,POST | `/class/discipline/from-attendance` | `discipline_from_attendance()` | 缺勤转违纪 |
| POST | `/class/discipline/<int:rid>/edit` | `edit_discipline(rid)` | 编辑违纪 |
| POST | `/class/discipline/<int:rid>/delete` | `delete_discipline(rid)` | 删除违纪 |
| POST | `/class/discipline/<int:rid>/resolve` | `resolve_discipline(rid)` | 标记已解决 |
| GET,POST | `/class/discipline/batch` | `batch_discipline()` | 批量添加违纪 |

### 考勤与请假
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET,POST | `/class/attendance` | `attendance_page()` | 今日考勤录入 |
| GET | `/class/attendance/history` | `attendance_history()` | 考勤历史 |
| GET | `/class/leaves` | `leave_list()` | 请假列表 |
| POST | `/class/leaves/<int:lid>/approve` | `approve_leave(lid)` | 审批请假 |

### 任务与通知
| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/class/tasks` | `task_list()` | 任务列表+反馈 |
| POST | `/class/tasks/<int:tid>/feedback` | `task_feedback(tid)` | 提交任务反馈 |
| GET,POST | `/class/notify` | `notify_parent()` | 通知家长 |

---

## 五、parent_portal — 家长端门户（16 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/parent/` | `dashboard()` | 家长首页 |
| GET | `/parent/attendance` | `attendance()` | 孩子考勤 |
| GET | `/parent/discipline` | `discipline()` | 孩子违纪 |
| GET | `/parent/scores` | `scores()` | 孩子成绩 |
| GET | `/parent/scores/trend` | `scores_trend()` | 成绩趋势图 |
| GET | `/parent/notices` | `notices()` | 通知公告 |
| POST | `/parent/notices/<int:nid>/read` | `mark_notice_read(nid)` | 标记已读 |
| POST | `/parent/notices/<int:nid>/sign` | `sign_notice(nid)` | 签名确认 |
| GET | `/parent/comments` | `comments()` | 期末评语 |
| GET | `/parent/meeting` | `meeting()` | 家长会 |
| POST | `/parent/meeting/<int:mid>/signin` | `meeting_signin(mid)` | 签到 |
| GET,POST | `/parent/leave/apply` | `leave_apply()` | 请假申请 |
| GET | `/parent/leaves` | `leave_list()` | 请假记录 |
| GET,POST | `/parent/appeal` | `appeal()` | 违纪申诉 |
| GET | `/parent/appeals` | `appeals()` | 申诉记录 |

---

## 六、common — 公共模块（9 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/common/messages` | `messages()` | 消息中心 |
| POST | `/common/messages/read/<int:msg_id>` | `mark_read(msg_id)` | 标记已读 |
| POST | `/common/messages/read_all` | `mark_all_read()` | 全部已读 |
| GET,POST | `/common/messages/compose` | `compose_message()` | 发送消息 |
| GET | `/common/announcements` | `announcements()` | 公告列表 |
| GET | `/common/api/events` | `sse_events()` | SSE实时推送 |
| GET | `/common/api/unread_count` | `api_unread_count()` | 未读消息数 |

---

## 七、api_miniapp — 小程序 API + JWT（22 路由）

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 登录获取 Token |
| POST | `/api/v1/auth/refresh` | 刷新 Token |

### 家长端
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/parent/dashboard` | 家长首页数据 |
| GET | `/api/v1/parent/scores` | 孩子成绩 |
| GET | `/api/v1/parent/discipline` | 孩子违纪 |
| POST | `/api/v1/parent/leave/apply` | 请假申请 |
| GET | `/api/v1/parent/leaves` | 请假记录 |
| GET | `/api/v1/parent/notices/unread` | 未读通知 |
| GET | `/api/v1/parent/psych/result` | 心理评估结果 |
| GET | `/api/v1/parent/endterm-comments` | 期末评语 |
| POST | `/api/v1/parent/feedback` | 家长反馈 |

### 推送
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/push/discipline` | 违纪通知推送 |
| POST | `/api/v1/push/score` | 成绩通知推送 |
| POST | `/api/v1/push/attendance` | 考勤通知推送 |

### 教师端
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/teacher/dashboard` | 教师首页 |
| GET | `/api/v1/teacher/students` | 学生列表 |
| POST | `/api/v1/teacher/discipline/add` | 添加违纪 |
| GET | `/api/v1/teacher/leaves/pending` | 待审批请假 |
| POST | `/api/v1/teacher/leaves/<int:lid>/approve` | 审批请假 |
| GET | `/api/v1/teacher/attendance/stats` | 考勤统计 |

### 年级组长
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/grade-leader/dashboard` | 年级首页 |

### 公共
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/announcements` | 公告列表 |
| GET | `/api/v1/messages` | 消息列表 |

---

## 八、wings — 五翼评价（11 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/wings/` | `dashboard()` | 五翼首页 |
| GET,POST | `/wings/score` | `score_page()` | 评分页面 |
| GET,POST | `/wings/score/teacher` | `score_teacher()` | 教师评分 |
| GET,POST | `/wings/score/parent` | `score_parent()` | 家长评分 |
| GET,POST | `/wings/score/student` | `score_student()` | 学生自评 |
| POST | `/wings/score/save` | `save_score()` | 保存评分 |
| GET | `/wings/class-ranking` | `class_ranking()` | 班级排名 |
| GET | `/wings/medals` | `medals()` | 勋章系统 |
| GET | `/wings/portfolio` | `portfolio()` | 学生档案 |
| GET | `/wings/portfolio/<int:sid>` | `portfolio_detail(sid)` | 档案详情 |
| GET | `/wings/analysis` | `analysis()` | 数据分析 |

---

## 九、quality — 综合素质评价（13 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/quality/` | `dashboard()` | 综合素质首页 |
| GET | `/quality/indicators` | `indicator_list()` | 指标管理 |
| GET,POST | `/quality/indicators/create` | `indicator_create()` | 创建指标 |
| GET,POST | `/quality/indicators/<int:iid>/edit` | `indicator_edit(iid)` | 编辑指标 |
| POST | `/quality/indicators/<int:iid>/toggle` | `indicator_toggle(iid)` | 启用/停用 |
| GET | `/quality/overview` | `overview()` | 全校总览 |
| GET | `/quality/class/<int:cid>` | `class_overview(cid)` | 班级总览 |
| GET,POST | `/quality/score` | `score()` | 评分 |
| POST | `/quality/batch-score` | `batch_score()` | 批量评分 |
| GET | `/quality/my-class` | `my_class()` | 我的班级 |
| GET,POST | `/quality/self-eval` | `self_eval()` | 自评 |
| GET,POST | `/quality/peer-eval` | `peer_eval()` | 互评 |
| GET | `/quality/report` | `report()` | 评价报告(雷达图) |

---

## 十、activity — 活动管理（20 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/activity/` | `index()` | 活动列表 |
| GET,POST | `/activity/create` | `create()` | 创建活动 |
| GET,POST | `/activity/<int:aid>/edit` | `edit(aid)` | 编辑活动 |
| GET | `/activity/<int:aid>` | `detail(aid)` | 活动详情 |
| POST | `/activity/<int:aid>/publish` | `publish(aid)` | 发布活动 |
| POST | `/activity/<int:aid>/complete` | `complete(aid)` | 完成活动 |
| POST | `/activity/<int:aid>/cancel` | `cancel_activity(aid)` | 取消活动 |
| POST | `/activity/<int:aid>/delete` | `delete(aid)` | 删除活动 |
| GET | `/activity/<int:aid>/registrations` | `registrations(aid)` | 报名列表 |
| POST | `/activity/<int:aid>/register` | `register_student(aid)` | 学生报名 |
| POST | `/activity/<int:aid>/cancel-registration` | `cancel_registration(aid)` | 取消报名 |
| POST | `/activity/<int:aid>/confirm/<int:rid>` | `confirm_registration(aid,rid)` | 确认报名 |
| POST | `/activity/<int:aid>/batch-register` | `batch_register(aid)` | 批量报名 |
| GET,POST | `/activity/<int:aid>/signin` | `signin(aid)` | 签到 |
| POST | `/activity/<int:aid>/signin-batch` | `signin_batch(aid)` | 批量签到 |
| POST | `/activity/<int:aid>/mark-absent` | `mark_absent(aid)` | 标记缺席 |
| GET | `/activity/<int:aid>/signin-stats` | `signin_stats(aid)` | 签到统计 |
| GET | `/activity/student/<int:sid>` | `student_list(sid)` | 学生活动列表 |
| GET | `/activity/student/<int:sid>/detail/<int:aid>` | `student_detail(sid,aid)` | 学生活动详情 |
| GET | `/activity/my-activities` | `my_activities()` | 我的活动 |

---

## 十一、scores — 成绩管理（16 路由）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/scores/` | `index()` | 成绩首页 |
| GET | `/scores/exams` | `exam_list()` | 考试列表 |
| GET,POST | `/scores/exams/create` | `create_exam()` | 创建考试 |
| POST | `/scores/exams/<int:eid>/delete` | `delete_exam(eid)` | 删除考试 |
| GET,POST | `/scores/exams/<int:eid>` | `exam_detail(eid)` | 考试详情+录入 |
| POST | `/scores/exams/<int:eid>/save` | `save_scores(eid)` | 保存成绩 |
| GET | `/scores/exams/<int:eid>/ranking` | `exam_ranking(eid)` | 排名 |
| GET | `/scores/exams/<int:eid>/analysis` | `exam_analysis(eid)` | 成绩分析 |
| GET | `/scores/subjects` | `subject_list()` | 科目列表 |
| GET,POST | `/scores/subjects/create` | `create_subject()` | 创建科目 |
| POST | `/scores/subjects/<int:sid>/delete` | `delete_subject(sid)` | 删除科目 |
| POST | `/scores/calculate-rank` | `calculate_rank()` | 计算排名 |
| GET | `/scores/comparison` | `comparison()` | 成绩对比 |
| POST | `/scores/batch-delete` | `batch_delete_scores()` | 批量删除 |
| POST | `/scores/<int:score_id>/delete` | `delete_score(score_id)` | 删除单条 |
| POST | `/scores/student/<int:sid>/delete` | `delete_student_scores(sid)` | 删除学生成绩 |

---

## 十二、其他功能蓝图路由

### notices — 通知公告（7 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/notices/` | 通知列表 |
| GET,POST | `/notices/create` | 创建通知 |
| POST | `/notices/<int:nid>/delete` | 删除通知 |
| GET | `/notices/<int:nid>/receipts` | 签收列表 |
| POST | `/notices/<int:nid>/read` | 标记已读 |
| POST | `/notices/<int:nid>/sign` | 签名确认 |

### system_config — 系统配置（10 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/system/` | 系统配置首页 |
| GET | `/system/semesters` | 学期列表 |
| GET,POST | `/system/semesters/create` | 创建学期 |
| GET,POST | `/system/semesters/<int:sid>/edit` | 编辑学期 |
| POST | `/system/semesters/<int:sid>/activate` | 激活学期 |
| POST | `/system/semesters/<int:sid>/delete` | 删除学期 |
| GET | `/system/config` | 配置项列表 |
| GET,POST | `/system/config/create` | 创建配置 |
| GET,POST | `/system/config/<int:cid>/edit` | 编辑配置 |
| POST | `/system/config/<int:cid>/delete` | 删除配置 |

### semester_archive — 学期归档（8 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/archive/` | 归档列表 |
| GET | `/archive/<int:aid>` | 归档详情 |
| POST | `/archive/create` | 创建归档 |
| POST | `/archive/<int:aid>/delete` | 删除归档 |
| POST | `/archive/<int:aid>/restore` | 恢复归档 |
| GET | `/archive/compare` | 学期对比 |
| GET | `/archive/api/compare` | 对比数据API |

### report_generator — 报表生成（5 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/reports/` | 报表列表 |
| POST | `/reports/generate` | 生成报表(Excel) |
| GET | `/reports/<int:rid>/view` | 查看报表 |
| GET | `/reports/<int:rid>/download` | 下载报表 |
| POST | `/reports/<int:rid>/delete` | 删除报表 |

### endterm_comment — 期末评语（6 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/endterm-comment/` | 评语列表 |
| GET,POST | `/endterm-comment/create` | 写评语 |
| GET,POST | `/endterm-comment/<int:cid>/edit` | 编辑评语 |
| POST | `/endterm-comment/<int:cid>/delete` | 删除评语 |
| GET,POST | `/endterm-comment/batch` | 批量评语 |
| GET | `/endterm-comment/export` | 导出(Word/HTML) |

### parent_meeting — 家长会（6 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/parent-meeting/` | 家长会列表 |
| GET,POST | `/parent-meeting/create` | 创建家长会 |
| GET | `/parent-meeting/<int:mid>` | 家长会详情 |
| POST | `/parent-meeting/<int:mid>/signin` | 签到 |
| POST | `/parent-meeting/<int:mid>/batch-signin` | 批量签到 |
| POST | `/parent-meeting/<int:mid>/delete` | 删除 |

### mental_health — 心理健康（6 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mental-health/` | 评估列表 |
| GET,POST | `/mental-health/create` | 创建评估 |
| GET | `/mental-health/<int:aid>` | 评估详情 |
| GET,POST | `/mental-health/<int:aid>/edit` | 编辑评估 |
| POST | `/mental-health/<int:aid>/delete` | 删除评估 |
| GET | `/mental-health/questions` | 题库管理 |

### survey — 心理问卷（6 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/survey/psych` | 问卷列表 |
| GET,POST | `/survey/psych/form` | 填写问卷 |
| POST | `/survey/psych/submit` | 提交问卷 |
| GET | `/survey/psych/stats` | 问卷统计 |
| GET | `/survey/parent` | 家长问卷 |
| GET | `/survey/analysis` | 问卷分析 |

### message_templates — 消息模板（5 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/message-templates/` | 模板列表 |
| GET,POST | `/message-templates/create` | 创建模板 |
| GET,POST | `/message-templates/<int:tid>/edit` | 编辑模板 |
| POST | `/message-templates/<int:tid>/delete` | 删除模板 |
| POST | `/message-templates/<int:tid>/use` | 使用模板发送 |

### backup — 数据备份（5 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/backup/` | 备份管理 |
| POST | `/backup/create` | 创建备份 |
| GET | `/backup/<int:bid>/download` | 下载备份 |
| POST | `/backup/<int:bid>/restore` | 恢复备份 |
| POST | `/backup/<int:bid>/delete` | 删除备份 |

### home_visit — 家访记录（4 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/home-visits/` | 家访列表 |
| GET,POST | `/home-visits/create` | 创建记录 |
| POST | `/home-visits/<int:vid>/delete` | 删除记录 |
| GET | `/home-visits/export` | 导出Excel |

### communication — 家校沟通（3 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/communication/` | 沟通记录 |
| POST | `/communication/remind` | 提醒家长 |
| GET | `/communication/api/stats` | 统计API |

### attendance_stats — 考勤统计（5 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/attendance-stats/` | 统计仪表盘 |
| GET | `/attendance-stats/class/<int:cid>` | 班级统计 |
| GET | `/attendance-stats/daily` | 每日趋势 |
| GET | `/attendance-stats/anomalies` | 异常预警 |
| GET | `/attendance-stats/student/<int:sid>` | 学生详情 |

### tags — 学生标签（3 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tags/` | 标签管理 |
| POST | `/tags/update` | 更新标签 |
| POST | `/tags/batch` | 批量标签 |

### workload — 教师工作量（3 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workload/` | 工作量总览 |
| GET | `/workload/<int:uid>` | 教师详情 |
| GET | `/workload/export` | 导出 |

### bigscreen — 数据大屏（2 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/bigscreen/` | 大屏展示 |
| GET | `/bigscreen/data` | 数据API |

### ai_analysis — AI 辅助分析（2 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ai-analysis/` | 分析首页(批量查询优化) |
| GET | `/ai-analysis/student/<int:sid>` | 学生详情 |

### export_summary — 导出汇总（2 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export-summary/` | 导出页面 |
| POST | `/export-summary/excel` | 导出Excel |

### audit — 审计日志（1 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/audit/` | 审计日志列表 |

### search — 全局搜索（5 路由）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/search/` | 搜索页 |
| GET | `/search/api` | 搜索API |
| GET | `/search/api/history` | 搜索历史 |
| POST | `/search/api/clear-history` | 清除历史 |

---

*文档生成时间: 2026-06-07*
