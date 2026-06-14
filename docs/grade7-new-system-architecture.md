# 梨江中学德育管理平台 (grade7-new) — 系统架构文档

> 版本: 1.0 | 最后更新: 2026-06-07 | 作者: 系统自动生成

---

## 一、系统概述

梨江中学德育管理平台是一套面向中学德育管理的 Web 应用系统，覆盖德育处、年级组、班主任、任课教师、家长、学生六类角色的完整工作流。

**核心业务流程**: 德育处下发任务 → 年级组分配 → 班主任执行 → 家长查看反馈

---

## 二、技术架构

### 2.1 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| Web 框架 | Flask | 3.1+ |
| ORM | SQLAlchemy | - |
| 数据库 | MySQL | 8.0 (Docker) |
| WSGI 服务器 | Gunicorn | gthread worker |
| 反向代理 | Nginx | 1.x |
| 前端 | Bootstrap + Chart.js + Jinja2 | - |
| 认证 | Session (Web) + JWT/HS256 (小程序) | PyJWT 2.10.1 |
| 容器化 | Docker Compose | v3 |
| 服务器 | Ubuntu (8.137.180.152) | 8GB RAM |

### 2.2 架构图

```
┌──────────────────────────────────────────────────────────┐
│                     Nginx :80                             │
│  (静态文件 /static/ + 反向代理 :5001)                       │
│  (rate limiting: login 5r/m, gzip, 16MB upload)          │
└─────────────────────┬────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│              Gunicorn :5001 (systemd)                     │
│  ┌──────────────────────────────────────────────────┐    │
│  │  workers: 2 × gthread (threads=4)                │    │
│  │  timeout: 120s, preload: ON                      │    │
│  │  pool_pre_ping: True, pool_recycle: 300          │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌─────────────── Flask Application ───────────────┐    │
│  │  31 Blueprints  →  blueprint_registry.py        │    │
│  │  decorators.py  →  @login_required + @require_role  │
│  │  scope_query()  →  按角色数据隔离               │    │
│  │  jwt_utils.py   →  JWT HS256 签发/验证          │    │
│  │  131 templates  →  Jinja2 (按角色渲染导航)      │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────┬────────────────────────────────────┘
                      │ sqlalchemy (pool_size=5, overflow=10)
┌─────────────────────▼────────────────────────────────────┐
│          MySQL 8.0 (Docker: grade7-new-db)               │
│  ┌──────────────────────────────────────────────────┐    │
│  │  IP: 172.30.0.2 (独立网络 grade7-new-network)     │    │
│  │  端口映射: 3307:3306                              │    │
│  │  内存限制: 400MB                                   │    │
│  │  performance_schema: OFF                           │    │
│  │  数据库: grade7_new (42 张表)                     │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 2.3 模块架构

```
grade7-new/
├── app.py                    # Flask 工厂 + 首页路由 + 健康检查
├── config.py                 # 配置（DB/Redis/上传/分页/JWT）
├── models.py                 # 42 个 SQLAlchemy ORM 模型
├── decorators.py             # 登录/角色/数据范围装饰器
├── blueprint_registry.py     # 31 蓝图集中注册
├── jwt_utils.py              # JWT Token 签发/验证/刷新
├── wsgi.py                   # Gunicorn 入口 (create_app)
├── blueprints/               # 31 个蓝图模块
│   ├── auth.py               # 认证（7 路由）
│   ├── ms.py                 # 德育处工作台（33 路由）
│   ├── grade.py              # 年级组工作台（12 路由）
│   ├── class_.py             # 班主任工作台（22 路由）
│   ├── parent_portal.py      # 家长端门户（16 路由）
│   ├── common.py             # 公共模块 + SSE 推送（9 路由）
│   ├── api_miniapp.py        # 小程序 API + JWT（22 路由）
│   ├── wings.py              # 五翼评价（11 路由）
│   ├── quality.py            # 综合素质评价（13 路由）
│   ├── activity.py           # 活动管理（20 路由）
│   ├── scores.py             # 成绩管理（16 路由）
│   ├── notices.py            # 通知公告（7 路由）
│   ├── system_config.py      # 系统配置（10 路由）
│   ├── semester_archive.py   # 学期归档（8 路由）
│   ├── report_generator.py   # 报表生成（5 路由）
│   ├── endterm_comment.py    # 期末评语（6 路由）
│   ├── parent_meeting.py     # 家长会（6 路由）
│   ├── survey.py             # 心理问卷（6 路由）
│   ├── mental_health.py      # 心理健康评估（6 路由）
│   ├── message_templates.py  # 消息模板（5 路由）
│   ├── backup.py             # 数据备份（5 路由）
│   ├── home_visit.py         # 家访记录（4 路由）
│   ├── communication.py      # 家校沟通追踪（3 路由）
│   ├── attendance_stats.py   # 考勤统计看板（5 路由）
│   ├── tags.py               # 学生标签（3 路由）
│   ├── workload.py           # 教师工作量（3 路由）
│   ├── bigscreen.py          # 数据大屏（2 路由）
│   ├── ai_analysis.py        # AI 辅助分析（2 路由）
│   ├── export_summary.py     # 导出汇总（2 路由）
│   ├── audit.py              # 审计日志（1 路由）
│   └── discipline_utils.py   # 纪律工具函数（共享）
├── templates/                # 131 个 Jinja2 模板
├── static/                   # CSS/JS/图片/报表
├── nginx/nginx.conf          # Nginx 配置（Docker 部署用）
├── Dockerfile                # Docker 镜像
├── docker-compose.yml        # Docker 编排
└── grade7-new.service        # systemd 服务文件
```

---

## 三、认证与权限体系

### 3.1 角色定义

| 角色 | 常量 | 数据范围 | 可见模块 |
|------|------|----------|----------|
| 德育处管理员 | `ms_admin` | 全校 | 全部 |
| 年级组长 | `grade_leader` | 本年级 | 年级工作台/班主任工作台 |
| 班主任 | `class_teacher` | 本班 | 班主任工作台/家长门户 |
| 任课教师 | `teacher` | 本年级 | 部分评分/查看 |
| 家长 | `parent` | 自家孩子 | 家长门户 |
| 学生 | `student` | 自己 | 基础查看 |

### 3.2 Web 端认证流程

```
用户 → 登录页 POST /login
  → auth.login_page() 验证用户名密码 (werkzeug.security)
  → session['user_id'], session['role'], session['grade_id'], session['class_id']
  → 按角色跳转对应工作台
  → 后续请求: @login_required 检查 session
  → @require_role('ms_admin') 检查角色权限
```

### 3.3 小程序端认证流程

```
微信小程序 → POST /api/v1/auth/login
  → 验证用户名密码
  → jwt_utils.create_token() 签发 JWT (HS256, 30天)
  → 返回 {token, user_info}
  → 后续请求: Authorization: Bearer <token>
  → jwt_utils.verify_token() 验证
```

### 3.4 数据隔离

`scope_query(model)` 装饰器自动按角色过滤:
- `ms_admin` → 查询全部
- `grade_leader` → 按 `grade_id` 过滤
- `class_teacher` → 按 `class_id` 过滤
- `parent` → 按 `bound_student_id` 过滤
- `student` → 按自身 `student_id` 过滤

---

## 四、数据库设计原则

1. **统一大表设计**: 所有模块共用一个数据库 `grade7_new`，42 张表全在同一库
2. **角色关联**: User 通过 `grade_id`/`class_id`/`bound_student_id` 绑定操作范围
3. **多级冗余**: 违纪/考勤/成绩等记录同时存储 `student_id` + `class_id` + `grade_id`，加速按层级查询
4. **软删除**: Grade/Class/Student 使用 `is_active` 标记，不物理删除
5. **外键**: 使用 SQLAlchemy ForeignKey 保证引用完整性
6. **索引**: 关键查询字段均已建索引（student_id, class_id, grade_id, record_date, status）

---

## 五、安全设计

### 5.1 已实现

| 措施 | 说明 |
|------|------|
| bcrypt 密码哈希 | werkzeug.security generate_password_hash/check_password_hash |
| Session HttpOnly | SESSION_COOKIE_HTTPONLY = True |
| CSRF 防护 | SESSION_COOKIE_SAMESITE = Lax |
| Nginx 限流 | login 端点 5r/m, burst 3 |
| 文件上传限制 | MAX_CONTENT_LENGTH = 16MB |
| 连接池保护 | pool_pre_ping + pool_recycle 300s |
| 审计日志 | 所有业务操作记录 AuditLog |

### 5.2 待加固

| 风险 | 建议 |
|------|------|
| MySQL 3307 暴露在 0.0.0.0 | 绑定 127.0.0.1 |
| 无 iptables | 配置 INPUT DROP + 白名单 |
| SSH 22 端口开放 | 更换端口或 fail2ban |

---

## 六、性能优化

| 优化项 | 说明 |
|--------|------|
| Gunicorn gthread | 2 workers × 4 threads，支持 SSE 长连接 |
| 连接池 | pool_size=5, max_overflow=10, pool_pre_ping=True |
| 批量查询 | AI 分析模块从 5446 次查询优化为 4 次批量查询 |
| MySQL 限制 | 400MB 内存限制, performance_schema=OFF |
| Gzip | Nginx 开启 gzip 压缩 |
| 静态资源 | 本地 url_for，禁止 CDN |

---

## 七、关键业务流程

### 7.1 违纪处理流程

```
班主任/德育处 → 添加违纪记录(DisciplineRecord)
  → discipline_utils.check_escalation() 自动升级检查
    轻微: 3次轻微 → 1次一般
    一般: 2次一般 → 1次严重
    严重: 2次严重 → 1次重大
  → discipline_utils.send_discipline_notifications() 自动推送
    → 班主任收到通知
    → 家长收到通知

家长 → 申诉(DisciplineAppeal)
  → 德育处 review → 通过/驳回
  → discipline_utils.send_appeal_notifications() 通知家长结果
```

### 7.2 请假审批流程

```
家长 → 提交请假申请(LeaveRequest)
  → 班主任审批 → class_approved
  → 年级组长审批 → grade_approved
  → 自动同步考勤记录(Attendance status='leave')
```

### 7.3 任务流转流程

```
德育处 → 创建任务(Task) → 指定目标(年级/班级/个人)
  → 目标用户查看 → 执行 → 提交反馈(TaskFeedback)
  → 德育处查看完成情况 → 关闭任务
```

### 7.4 消息推送流程 (SSE)

```
任何角色 → compose_message / send_notification()
  → 写入 Message 表
  → push_event(to_user_id, data) 推入 Redis 频道
  → SSE Generator → EventSource 实时推送到浏览器
```

---

## 八、部署拓扑

```
服务器: 8.137.180.152 (Ubuntu, 8GB RAM)

┌─────────────────────────────────────┐
│            Nginx :80                │
│    /etc/nginx/sites-enabled/grade7  │
│    rate limiting: login 5r/m        │
└──────────────┬──────────────────────┘
               │ proxy_pass
┌──────────────▼──────────────────────┐
│     Gunicorn :5001 (systemd)        │
│     /opt/grade7-new/venv/           │
│     /etc/systemd/system/grade7-new  │
└──────────────┬──────────────────────┘
               │ sqlalchemy
┌──────────────▼──────────────────────┐
│  MySQL 8.0 (Docker)                 │
│  Container: grade7-new-db           │
│  Network: grade7-new-network        │
│  Port: 3307:3306                    │
└─────────────────────────────────────┘
```

---

## 九、系统规模统计

| 指标 | 数量 |
|------|------|
| 蓝图 (Blueprint) | 31 |
| 路由 (Route) | ~250+ |
| 数据表 | 42 |
| 模板文件 | 131 |
| Python 源码文件 | 35 |
| 角色类型 | 6 |
| 总代码行数 (估) | ~15,000+ |

---

*文档生成时间: 2026-06-07 | 基于 grade7-new 生产环境代码*
