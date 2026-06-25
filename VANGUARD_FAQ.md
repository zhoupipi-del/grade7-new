# 先遣队实战操作 FAQ 故障排查手册 v1.0

> Phase A D2 · 2026-06-25 · 基于已知模块特性 + 真实前线Bug预判
> 随 D2-D3 真实摩擦力冒出来持续填充

---

## 一、登录与认证

### Q1: 登录后页面空白 / 一直跳转登录页
**排查**: 检查浏览器 Cookie 是否被禁用。Wings 3.0 用 `access_token` Cookie 桥接旧 Flask 前端，禁用 Cookie 会导致 301 循环。
**解决**: 允许 `lijiangschool.online` 的 Cookie。

### Q2: admin 账号登录提示"用户名或密码错误"
**背景**: P0安全加固后密码收紧。
**解决**: admin 密码已同步为 `admin123`（与 grade7_leader 一致）。如仍失败，DB 重置：
```sql
UPDATE users SET password_hash=(SELECT password_hash FROM (SELECT password_hash FROM users WHERE username='grade7_leader') t), password_change_required=0 WHERE username='admin';
```

---

## 二、德育大数据看板 `/ms/moral-radar`

### Q3: 看板三张图都不显示 / 显示"加载失败"
**排查**: F12 控制台看 `fetch` 请求状态码。
- `401` → Cookie 过期，重新登录
- `404` → Nginx 路由未包含 `dashboard`，检查 `/etc/nginx/sites-enabled/grade7` 正则
- `500` → Wings 3.0 后端报错，查 `journalctl -u wings3`

### Q4: 班主任登录看板只看到1个班级
**这是正常的 RBAC 隔离**，不是Bug。班主任严禁横向查看其他班级隐私数据。年级组长看本年级全部，德育处看全校。

### Q5: 四象限散点图某些学生没有点
**原因**: 跨库桥接时，该学生在 wings3 有德育分但旧库 grade7_new.scores 无成绩记录（或反之），`student_id` 不匹配则跳过。
**排查**:
```sql
SELECT s.id FROM wings3.students s LEFT JOIN grade7_new.scores sc ON s.id=sc.student_id WHERE sc.student_id IS NULL;
```

---

## 三、违纪录入与滑窗孵化

### Q6: 录入违纪后没有自动生成处分草稿
**排查**: 滑窗规则是"30天内3次 serious 违纪"才触发。minor/warning 不触发。
**验证红线候选**:
```sql
SELECT student_id, COUNT(*) FROM discipline_records
WHERE school_id=1 AND type='serious' AND incident_date >= CURDATE() - INTERVAL 30 DAY
GROUP BY student_id HAVING COUNT(*) >= 3;
```
如结果为空，说明还没人踩红线，属正常。

### Q7: 处分草稿状态 `DRAFT_PENDING` 怎么推进
**流程**: 班主任提交 → 年级组长 `/approve` → 德育处 `/approve` 终审 → `ACTIVE`。两级审批缺一不可。

---

## 四、通知红点

### Q8: 通知红点不消失
**排查**: 红点靠轮询 `/api/v1/notifications/unread-count`。点击通知后调 `/api/v1/notifications/{id}/read` 标记已读。如红点不消失，检查 JS console 有无 fetch 报错。

### Q9: 家长收不到申诉结果通知
**排查**: 申诉复核后通知推送给班主任+年级组长（ACCEPTED）或班主任（REJECTED）。家长端暂无直接通知，需班主任线下转达。

---

## 五、成长档案（已修复Bug）

### Q10: 学生成长档案详情页报500错误 ✅ 已修复
**真实Bug** (2026-06-25 22:12 发现): `/growth/detail/{id}` 访问 `DisciplineRecord.reason` 但表字段是 `description`。
**修复**: `growth_report.py` L86 `r.reason` → `r.description`。
**教训**: 旧 Flask 模型字段名与表字段不一致时，以表结构为准。

---

## 六、家校申诉 Webhook

### Q11: Webhook 推送返回 401
**原因**: `X-Webhook-Secret` 请求头缺失或错误。密钥在 `/root/backend/.env` 的 `WEBHOOK_SECRET`。

### Q12: 重复推送返回 `created: false`
**这是正常的幂等防重**，不是Bug。相同 `idempotency_key` 的重复请求不会创建新申诉记录。

### Q13: 申诉通过后处分状态没变
**排查**: 申诉 ACCEPTED 应自动将处分 `ACTIVE → REVOKED`。如未变，查 `journalctl -u wings3` 看有无事务回滚。

---

## 七、数据隔离

### Q14: 班主任能看到其他班级的数据
**这是严重Bug，应立即上报**。所有 wings3 端点通过 `user.class_id` 过滤。如发生越权，检查 router 层是否遗漏 `class_id` 守卫。

---

## 附录：一键瞭望哨

```bash
cd /c/Users/Administrator/WorkBuddy/2026-05-26-20-55-49/backend
python vanguard_watchdog.py
```

输出：系统健康度 + 滑窗Hook状态 + D2数据哨位 + 通知分布 + 错误扫描 + 资源占用

---

## 待填充（D2-D3 真实问题冒出后补充）

- [ ] 家长端小程序对接问题
- [ ] 考勤导入格式问题
- [ ] PDF导出超时
- [ ] Celery任务堆积
