#!/usr/bin/env python3
"""
教研铁三角测试流水注入脚本
按三条状态机顺序走完整闭环:
  1. 集体备课: DRAFT → COLLECTIVE_REVIEW → ADMIN_APPROVE → PUBLISHED + Fork
  2. 听课评课: PENDING → APPEALED → RESOLVED (申诉路径)
  3. 听课评课: PENDING → CONFIRMED (确认路径)
  4. 教研活动: PLANNED → IN_PROGRESS → COMPLETED (双向血缘)
"""

import sys
from datetime import datetime, timedelta

import requests

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 15

# ── 测试账号 ──
ACCOUNTS = {
    "admin": {"username": "admin", "password": "admin123"},
    "leader": {"username": "grade7_leader", "password": "admin123"},
    "teacher": {"username": "ct_2501", "password": "admin123"},
}


# ── 颜色输出 ──
def green(t):
    print(f"\033[92m{t}\033[0m")


def yellow(t):
    print(f"\033[93m{t}\033[0m")


def red(t):
    print(f"\033[91m{t}\033[0m")


def cyan(t):
    print(f"\033[96m{t}\033[0m")


def bold(t):
    print(f"\033[1m{t}\033[0m")


# ── 登录 ──
def login(role: str):
    creds = ACCOUNTS[role]
    resp = requests.post(f"{BASE}/auth/login", json=creds, timeout=TIMEOUT)
    if resp.status_code != 200:
        red(f"  ✗ 登录失败 [{role}]: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    user = data.get("user", {})
    uid = user.get("id", 0)
    green(f"  ✓ [{role}] 登录成功, user_id={uid}, role={user.get('role', '?')}")
    return token, uid


def api(method: str, path: str, token: str, data=None):
    url = f"{BASE}/{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.request(method, url, json=data, headers=headers, timeout=TIMEOUT)
    return resp


def check(resp, label, expect=None):
    if expect is None:
        expect = 200 if resp.request.method == "GET" else 200
        # 201 for POST creates
        if resp.status_code == 201:
            expect = 201
    if resp.status_code == expect:
        green(f"  ✓ {label}: {resp.status_code}")
        return True
    else:
        red(f"  ✗ {label}: {resp.status_code} {resp.text[:300]}")
        return False


# ═══════════════════════════════════════════════════════════════
# 1. 集体备课状态机
# ═══════════════════════════════════════════════════════════════
def test_lesson_prep(tokens, uids):
    bold("\n══ 1. 集体备课状态机 ══")
    t_token, t_id = tokens["teacher"], uids["teacher"]
    l_token, l_id = tokens["leader"], uids["leader"]
    a_token = tokens["admin"]

    # 1a. 教师创建教案 (DRAFT)
    cyan("\n[1a] 教师创建教案 (DRAFT)...")
    plan_data = {
        "title": "七年级数学《一元一次方程的解法》集体备课",
        "description": "初一数学组集体备课——一元一次方程解法专题",
        "subject_code": "math",
        "grade_level": "grade_7",
        "lesson_type": "new",
        "duration": 2,
        "tags": ["方程", "初一", "集体备课"],
        "change_log": "初始创建",
        "content": {
            "teaching_objectives": [
                "掌握一元一次方程的概念",
                "熟练运用移项、合并同类项解一元一次方程",
                "能将实际问题转化为一元一次方程",
            ],
            "key_points": ["移项法则", "合并同类项"],
            "difficulties": ["含有分母的一元一次方程解法"],
            "teaching_methods": ["讲授法", "练习法", "讨论法"],
            "teaching_process": [
                {
                    "phase": "导入",
                    "duration": 5,
                    "content": "复习等式性质，引出方程概念",
                    "activities": ["提问", "回顾"],
                    "resources": ["PPT"],
                },
                {
                    "phase": "新授",
                    "duration": 20,
                    "content": "讲解移项法则和合并同类项",
                    "activities": ["讲授", "板演"],
                    "resources": ["教材", "微课"],
                },
                {
                    "phase": "练习",
                    "duration": 15,
                    "content": "分层练习题",
                    "activities": ["独立练习", "同桌互批"],
                    "resources": ["练习单"],
                },
                {
                    "phase": "小结",
                    "duration": 3,
                    "content": "归纳解方程步骤",
                    "activities": ["学生总结"],
                    "resources": [],
                },
                {
                    "phase": "作业",
                    "duration": 2,
                    "content": "课本P102 练习1-5题",
                    "activities": [],
                    "resources": [],
                },
            ],
            "homework": ["课本P102 练习1-5题", "拓展: 思考分母方程解法"],
            "blackboard_design": "一元一次方程解法\\n1. 移项\\n2. 合并同类项\\n3. 系数化为1",
            "reflection": "",
        },
    }
    resp = api("POST", "research_lesson_prep/", t_token, plan_data)
    if not check(resp, "创建教案"):
        return None
    plan = resp.json()
    plan_id = plan["id"]
    yellow(f"    plan_id={plan_id}, status={plan['status']}, version={plan['current_version']}")

    # 1b. 教师创建V2 (大版本修订)
    cyan("\n[1b] 教师创建V2 (大版本修订)...")
    v2_content = {
        "teaching_objectives": [
            "掌握一元一次方程的概念",
            "熟练运用移项、合并同类项解一元一次方程",
            "能将实际问题转化为一元一次方程",
            "体会化归思想在解方程中的应用",  # 新增
        ],
        "key_points": ["移项法则", "合并同类项", "化归思想"],
        "difficulties": ["含有分母的一元一次方程解法", "实际问题建模"],
        "teaching_methods": ["讲授法", "练习法", "讨论法", "情境导入法"],
        "teaching_process": [
            {
                "phase": "导入",
                "duration": 5,
                "content": "情境引入: 鸡兔同笼问题",
                "activities": ["情境创设", "提问"],
                "resources": ["PPT", "动画"],
            },
            {
                "phase": "新授",
                "duration": 25,
                "content": "讲解移项、合并同类项、系数化为1，含分母方程示范",
                "activities": ["讲授", "板演", "小组讨论"],
                "resources": ["教材", "微课", "几何画板"],
            },
            {
                "phase": "练习",
                "duration": 10,
                "content": "分层练习: 基础题+提高题",
                "activities": ["独立练习", "上台展示"],
                "resources": ["练习单"],
            },
            {
                "phase": "小结",
                "duration": 3,
                "content": "归纳解方程四步法",
                "activities": ["学生总结"],
                "resources": [],
            },
            {
                "phase": "作业",
                "duration": 2,
                "content": "基础题+拓展题分层布置",
                "activities": [],
                "resources": [],
            },
        ],
        "homework": ["课本P102 练习1-5题(基础)", "拓展: 实际问题建模1题", "预习: 二元一次方程组"],
        "blackboard_design": "一元一次方程解法\\nStep1: 去分母\\nStep2: 去括号\\nStep3: 移项\\nStep4: 合并同类项\\nStep5: 系数化为1",
        "reflection": "",
    }
    resp = api(
        "POST",
        f"research_lesson_prep/{plan_id}/versions",
        t_token,
        {
            "content": v2_content,
            "change_log": "增加化归思想目标, 新增情境导入, 细化分层练习",
            "is_major": True,
        },
    )
    if check(resp, "创建V2"):
        yellow(
            f"    version_number={resp.json()['version_number']}, is_major={resp.json()['is_major']}"
        )

    # 1c. 教师提交集体评议 (DRAFT → COLLECTIVE_REVIEW)
    cyan("\n[1c] 教师提交集体评议 (DRAFT → REVIEW)...")
    resp = api("POST", f"research_lesson_prep/{plan_id}/submit", t_token)
    if check(resp, "提交评议"):
        yellow(f"    status={resp.json()['status']}")

    # 1d. 组长添加3条批注 (不同严重度)
    cyan("\n[1d] 组长添加3条批注 (suggestion/issue/critical)...")
    reviews = [
        {
            "version_number": 2,
            "target_section": "teaching_objectives",
            "target_anchor": "item_3",
            "comment": "第三个目标'将实际问题转化为方程'建议拆分为更具体的能力指标，如'能从行程问题中提取等量关系'",
            "severity": "suggestion",
        },
        {
            "version_number": 2,
            "target_section": "teaching_process",
            "target_anchor": "step_2",
            "comment": "新授环节25分钟偏长，建议压缩至20分钟，将节省的时间用于练习环节的师生共评",
            "severity": "issue",
        },
        {
            "version_number": 2,
            "target_section": "homework",
            "target_anchor": "item_2",
            "comment": "拓展题'实际问题建模'缺少梯度支架，初一学生直接建模困难较大，建议增加中间引导步骤",
            "severity": "critical",
        },
    ]
    review_ids = []
    for i, rev in enumerate(reviews):
        resp = api("POST", f"research_lesson_prep/{plan_id}/reviews", l_token, rev)
        if check(resp, f"批注{i + 1} ({rev['severity']})"):
            review_ids.append(resp.json()["id"])

    # 1e. 组长解决1条批注
    cyan("\n[1e] 组长解决批注#1 (suggestion)...")
    if review_ids:
        resp = api(
            "PUT",
            f"research_lesson_prep/{plan_id}/reviews/{review_ids[0]}",
            l_token,
            {"resolution_note": "已采纳建议，将目标拆分为两个具体指标"},
        )
        check(resp, "解决批注")

    # 1f. 查看未解决批注数
    cyan("\n[1f] 查看教案详情 (未解决批注数)...")
    resp = api("GET", f"research_lesson_prep/{plan_id}", t_token)
    if check(resp, "教案详情"):
        yellow(f"    unresolved_review_count={resp.json().get('unresolved_review_count', '?')}")

    # 1g. 组长审核通过 (REVIEW → APPROVED)
    cyan("\n[1g] 组长审核通过 (REVIEW → APPROVED)...")
    resp = api("POST", f"research_lesson_prep/{plan_id}/approve", l_token)
    if check(resp, "审核通过"):
        yellow(f"    status={resp.json()['status']}")

    # 1h. 管理员发布 (APPROVED → PUBLISHED)
    cyan("\n[1h] 管理员发布 (APPROVED → PUBLISHED)...")
    resp = api("POST", f"research_lesson_prep/{plan_id}/publish", a_token)
    if check(resp, "发布"):
        yellow(
            f"    status={resp.json()['status']}, published_version={resp.json().get('published_version')}"
        )

    # 1i. 教师Fork已发布教案
    cyan("\n[1i] 教师 Fork 已发布教案...")
    resp = api(
        "POST",
        f"research_lesson_prep/{plan_id}/fork",
        t_token,
        {"title": "七年级数学《一元一次方程》二次备课(个性化修改)"},
    )
    if check(resp, "Fork派生"):
        forked = resp.json()
        yellow(
            f"    forked_plan_id={forked['id']}, forked_from_id={forked.get('forked_from_id')}, status={forked['status']}"
        )

    # 1j. 查看版本历史
    cyan("\n[1j] 查看版本历史...")
    resp = api("GET", f"research_lesson_prep/{plan_id}/versions", t_token)
    if check(resp, "版本历史"):
        versions = resp.json().get("items", [])
        yellow(f"    共{len(versions)}个版本:")
        for v in versions:
            tag = " [大版本]" if v.get("is_major") else ""
            yellow(
                f"      V{v['version_number']}: {v.get('change_log', '?')}{tag} (by {v.get('editor_name', '?')})"
            )

    # 1k. Dashboard
    cyan("\n[1k] 教研看板统计...")
    resp = api("GET", "research_lesson_prep/dashboard", t_token)
    if check(resp, "Dashboard"):
        d = resp.json()
        yellow(
            f"    total={d['total_plans']}, draft={d['draft_count']}, review={d['review_count']}, approved={d['approved_count']}, published={d['published_count']}"
        )

    return plan_id


# ═══════════════════════════════════════════════════════════════
# 2. 听课评课状态机 — 申诉路径
# ═══════════════════════════════════════════════════════════════
def test_observation_appeal(tokens, uids, plan_id):
    bold("\n══ 2. 听课评课状态机 — 申诉路径 ══")
    l_token, l_id = tokens["leader"], uids["leader"]
    t_id = uids["teacher"]

    # 2a. 组长创建听课记录 (关联教案)
    cyan("\n[2a] 组长创建听课记录 (关联教案)...")
    obs_data = {
        "teacher_id": t_id,
        "class_id": 1,
        "subject_code": "math",
        "lesson_title": "一元一次方程的解法(第二课时)",
        "observation_type": "routine",
        "lesson_plan_id": plan_id,
        "plan_version_number": 2,
        "observed_at": (datetime.now() - timedelta(days=1)).isoformat(),
        "duration_minutes": 45,
        "plan_adherence": "partial",
        "plan_deviation_note": "导入环节超时5分钟, 练习环节少做了1道提高题",
        "text_feedback": {
            "highlights": ["情境引入效果好, 学生参与度高", "板书规范, 逻辑清晰"],
            "suggestions": ["建议增加课堂练习时间", "关注后进生个别辅导"],
            "overall_comment": "整体教学效果良好, 基本达成教学目标, 建议优化时间分配",
        },
    }
    resp = api("POST", "research_observation/", l_token, obs_data)
    if not check(resp, "创建听课记录"):
        return None
    obs = resp.json()
    obs_id = obs["id"]
    yellow(
        f"    obs_id={obs_id}, feedback_status={obs['feedback_status']}, lesson_plan_id={obs.get('lesson_plan_id')}"
    )

    # 2b. 组长提交评分矩阵
    cyan("\n[2b] 组长提交多维评分矩阵...")
    rubric_data = {
        "template_name": "梨江中学常规听课评分表",
        "dimensions": [
            {
                "name": "教学目标",
                "score": 8.5,
                "max": 10,
                "weight": 0.15,
                "comment": "目标明确, 但化归思想渗透不够",
            },
            {
                "name": "教学内容",
                "score": 9.0,
                "max": 10,
                "weight": 0.20,
                "comment": "内容准确, 重点突出",
            },
            {
                "name": "教学方法",
                "score": 7.5,
                "max": 10,
                "weight": 0.15,
                "comment": "讲授为主, 互动偏少",
            },
            {
                "name": "教学过程",
                "score": 7.0,
                "max": 10,
                "weight": 0.20,
                "comment": "时间分配欠佳, 导入超时",
            },
            {
                "name": "教学效果",
                "score": 8.0,
                "max": 10,
                "weight": 0.15,
                "comment": "多数学生掌握, 少数需巩固",
            },
            {
                "name": "教师素养",
                "score": 9.5,
                "max": 10,
                "weight": 0.15,
                "comment": "板书规范, 语言表达清晰",
            },
        ],
    }
    resp = api("POST", f"research_observation/{obs_id}/rubric", l_token, rubric_data)
    if check(resp, "提交评分"):
        r = resp.json()
        yellow(
            f"    total_score={r['total_score']}/{r['max_score']}, percentage={r['percentage']}%"
        )

    # 2c. 教师申诉 (PENDING → APPEALED)
    cyan("\n[2c] 教师提出申诉 (PENDING → APPEALED)...")
    resp = api(
        "POST",
        f"research_observation/{obs_id}/appeal",
        tokens["teacher"],
        {
            "appeal_reason": "教学过程维度评分偏低, 导入超时是因为学生课前预习不充分导致回顾环节延长, 非教学设计问题。另外建议重新审视教学方法维度的评分, 本课采用了小组讨论和上台展示两种互动形式。",
            "appealed_dimensions": ["教学过程", "教学方法"],
        },
    )
    if check(resp, "教师申诉"):
        yellow(f"    feedback_status={resp.json()['feedback_status']}")

    # 2d. 查看申诉历史
    cyan("\n[2d] 查看反馈/申诉历史...")
    resp = api("GET", f"research_observation/{obs_id}/appeals", tokens["teacher"])
    if check(resp, "申诉历史"):
        appeals = resp.json().get("items", [])
        yellow(f"    共{len(appeals)}条记录:")
        for a in appeals:
            yellow(f"      action={a['action_type']}, reason={a.get('appeal_reason', '')[:50]}...")

    # 2e. 组长处理申诉 (APPEALED → RESOLVED)
    cyan("\n[2e] 组长处理申诉 (APPEALED → RESOLVED)...")
    resp = api(
        "POST",
        f"research_observation/{obs_id}/resolve",
        l_token,
        {
            "resolution": "经组内讨论, 导入超时确有客观原因(学生预习不足), 教学过程维度评分上调至8.0。教学方法维度维持原评, 小组讨论时长不足5分钟, 互动深度有限。总分调整为81.25分。",
            "score_adjusted": True,
            "adjusted_total_score": 81.25,
        },
    )
    if check(resp, "处理申诉"):
        yellow(
            f"    feedback_status={resp.json()['feedback_status']}, score={resp.json().get('score_total')}"
        )

    return obs_id


# ═══════════════════════════════════════════════════════════════
# 3. 听课评课状态机 — 确认路径
# ═══════════════════════════════════════════════════════════════
def test_observation_confirm(tokens, uids, plan_id):
    bold("\n══ 3. 听课评课状态机 — 确认路径 ══")
    l_token, l_id = tokens["leader"], uids["leader"]
    t_id = uids["teacher"]

    # 3a. 创建第二条听课记录
    cyan("\n[3a] 创建第二条听课记录 (复习课)...")
    obs_data = {
        "teacher_id": t_id,
        "class_id": 1,
        "subject_code": "math",
        "lesson_title": "一元一次方程复习课",
        "observation_type": "special",
        "lesson_plan_id": plan_id,
        "observed_at": datetime.now().isoformat(),
        "duration_minutes": 40,
        "plan_adherence": "full",
        "text_feedback": {
            "highlights": ["复习课结构完整", "学生练习充分", "归纳总结到位"],
            "suggestions": [],
            "overall_comment": "复习课效果优秀, 学生掌握扎实",
        },
    }
    resp = api("POST", "research_observation/", l_token, obs_data)
    if not check(resp, "创建听课记录"):
        return None
    obs_id = resp.json()["id"]
    yellow(f"    obs_id={obs_id}, feedback_status={resp.json()['feedback_status']}")

    # 3b. 提交评分
    cyan("\n[3b] 提交评分矩阵...")
    resp = api(
        "POST",
        f"research_observation/{obs_id}/rubric",
        l_token,
        {
            "template_name": "梨江中学复习课评分表",
            "dimensions": [
                {"name": "教学目标", "score": 9.5, "max": 10, "comment": "复习目标明确, 全面覆盖"},
                {
                    "name": "教学内容",
                    "score": 9.0,
                    "max": 10,
                    "comment": "知识梳理系统, 典型题选取精当",
                },
                {"name": "教学方法", "score": 9.0, "max": 10, "comment": "讲练结合, 方法多样"},
                {"name": "教学过程", "score": 9.5, "max": 10, "comment": "节奏紧凑, 过渡自然"},
                {"name": "教学效果", "score": 9.5, "max": 10, "comment": "学生参与度高, 正确率高"},
                {"name": "教师素养", "score": 9.5, "max": 10, "comment": "课堂掌控力强"},
            ],
        },
    )
    if check(resp, "提交评分"):
        yellow(
            f"    total={resp.json()['total_score']}/{resp.json()['max_score']}, {resp.json()['percentage']}%"
        )

    # 3c. 教师确认 (PENDING → CONFIRMED)
    cyan("\n[3c] 教师确认评课 (PENDING → CONFIRMED)...")
    resp = api("POST", f"research_observation/{obs_id}/confirm", tokens["teacher"])
    if check(resp, "教师确认"):
        yellow(f"    feedback_status={resp.json()['feedback_status']}")

    return obs_id


# ═══════════════════════════════════════════════════════════════
# 4. 教研活动状态机
# ═══════════════════════════════════════════════════════════════
def test_activities(tokens, uids, plan_id, obs_id_appeal, obs_id_confirm):
    bold("\n══ 4. 教研活动状态机 ══")
    l_token, l_id = tokens["leader"], uids["leader"]
    t_id = uids["teacher"]
    a_id = uids["admin"]

    # 4a. 创建教研活动 (PLANNED)
    cyan("\n[4a] 创建教研活动 (PLANNED)...")
    act_data = {
        "title": "初一数学组第七周集体教研: 一元一次方程教学研讨",
        "description": "围绕一元一次方程教学, 开展备课研讨、听课评议、教学改进讨论",
        "activity_type": "regular_meeting",
        "subject_code": "math",
        "grade_level": "grade_7",
        "planned_at": (datetime.now() + timedelta(days=1)).isoformat(),
        "planned_end_at": (datetime.now() + timedelta(days=1, hours=2)).isoformat(),
        "location": "教学楼三楼会议室",
        "linked_plan_ids": [plan_id] if plan_id else [],
        "linked_observation_ids": [x for x in [obs_id_appeal, obs_id_confirm] if x],
        "participant_ids": [t_id, a_id],
    }
    resp = api("POST", "research_activities/", l_token, act_data)
    if not check(resp, "创建活动"):
        return None
    act = resp.json()
    act_id = act["id"]
    yellow(
        f"    act_id={act_id}, status={act['status']}, participants={act['participant_count']}, agendas={act['agenda_count']}"
    )
    yellow(
        f"    linked_plans={act.get('linked_plan_ids')}, linked_observations={act.get('linked_observation_ids')}"
    )

    # 4b. 添加议题1 (关联教案)
    cyan("\n[4b] 添加议题1: 备课方案研讨 (关联教案)...")
    resp = api(
        "POST",
        f"research_activities/{act_id}/agendas",
        l_token,
        {
            "title": "《一元一次方程解法》备课方案集体研讨",
            "presenter_id": t_id,
            "content": "由备课人介绍设计思路, 组内讨论教学目标设定、重难点突破、分层练习设计等",
            "planned_duration": 30,
            "linked_plan_id": plan_id,
        },
    )
    if check(resp, "议题1"):
        agenda1_id = resp.json()["id"]
        yellow(
            f"    agenda_id={agenda1_id}, seq={resp.json()['seq']}, linked_plan={resp.json().get('linked_plan_id')}"
        )

    # 4c. 添加议题2 (关联听课)
    cyan("\n[4c] 添加议题2: 听课评议 (关联听课记录)...")
    resp = api(
        "POST",
        f"research_activities/{act_id}/agendas",
        l_token,
        {
            "title": "听课评议: 一元一次方程课堂教学反馈",
            "presenter_id": l_id,
            "content": "针对本周听课情况进行反馈评议, 讨论教学改进方向",
            "planned_duration": 25,
            "linked_observation_id": obs_id_appeal,
        },
    )
    if check(resp, "议题2"):
        agenda2_id = resp.json()["id"]
        yellow(
            f"    agenda_id={agenda2_id}, seq={resp.json()['seq']}, linked_observation={resp.json().get('linked_observation_id')}"
        )

    # 4d. 添加议题3
    cyan("\n[4d] 添加议题3: 下周教学计划...")
    resp = api(
        "POST",
        f"research_activities/{act_id}/agendas",
        l_token,
        {
            "title": "第八周教学进度与分工安排",
            "presenter_id": l_id,
            "content": "讨论下周教学进度, 安排备课分工",
            "planned_duration": 15,
        },
    )
    if check(resp, "议题3"):
        yellow(f"    agenda_id={resp.json()['id']}, seq={resp.json()['seq']}")

    # 4e. 启动活动 (PLANNED → IN_PROGRESS)
    cyan("\n[4e] 启动活动 (PLANNED → IN_PROGRESS)...")
    resp = api("POST", f"research_activities/{act_id}/start", l_token)
    if check(resp, "启动活动"):
        yellow(f"    status={resp.json()['status']}")

    # 4f. 更新参与人签到
    cyan("\n[4f] 更新参与人签到状态...")
    resp = api("GET", f"research_activities/{act_id}/participants", l_token)
    if check(resp, "获取参与人列表"):
        participants = resp.json().get("items", [])
        for p in participants:
            resp2 = api(
                "PUT",
                f"research_activities/{act_id}/participants/{p['id']}",
                l_token,
                {"attendance_status": "checked_in", "check_in_at": datetime.now().isoformat()},
            )
            check(resp2, f"签到 {p.get('user_name', '?')}")

    # 4g. 更新议题讨论结果
    cyan("\n[4g] 更新议题1讨论结果...")
    resp = api("GET", f"research_activities/{act_id}/agendas", l_token)
    if check(resp, "获取议题列表"):
        agendas = resp.json().get("items", [])
        if agendas:
            resp2 = api(
                "PUT",
                f"research_activities/{act_id}/agendas/{agendas[0]['id']}",
                l_token,
                {
                    "actual_duration": 28,
                    "decision": "一致通过备课方案V2, 建议补充化归思想渗透策略, 分层练习增加C层(基础)题目比例",
                    "status": "resolved",
                },
            )
            if check(resp2, "更新议题1"):
                yellow(f"    decision={resp2.json().get('decision', '')[:60]}...")

    # 4h. 更新议题2讨论结果
    cyan("\n[4h] 更新议题2讨论结果...")
    if len(agendas) > 1:
        resp2 = api(
            "PUT",
            f"research_activities/{act_id}/agendas/{agendas[1]['id']}",
            l_token,
            {
                "actual_duration": 30,
                "decision": "申诉处理结论: 教学过程维度评分上调, 总分调整至81.25分。建议后续关注课堂时间管理, 课前预习检查制度化。",
                "status": "resolved",
            },
        )
        if check(resp2, "更新议题2"):
            yellow(f"    decision={resp2.json().get('decision', '')[:60]}...")

    # 4i. 完成活动 (IN_PROGRESS → COMPLETED)
    cyan("\n[4i] 完成活动 (IN_PROGRESS → COMPLETED)...")
    resp = api(
        "PUT",
        f"research_activities/{act_id}",
        l_token,
        {
            "summary": "本次教研活动围绕一元一次方程教学展开, 完成备课方案研讨和听课评议两个核心议题。备课方案V2获一致通过, 听课申诉得到妥善处理。下周继续推进二元一次方程组教学。",
            "decisions": [
                "备课方案V2通过, 补充化归思想策略",
                "听课评分调整至81.25分",
                "课前预习检查制度化",
                "下周由张老师负责二元一次方程组备课",
            ],
        },
    )
    check(resp, "更新活动摘要")

    resp = api("POST", f"research_activities/{act_id}/complete", l_token)
    if check(resp, "完成活动"):
        yellow(f"    status={resp.json()['status']}")

    # 4j. Dashboard
    cyan("\n[4j] 教研活动看板...")
    resp = api("GET", "research_activities/dashboard", l_token)
    if check(resp, "Dashboard"):
        d = resp.json()
        yellow(
            f"    total={d['total_activities']}, planned={d['planned']}, in_progress={d['in_progress']}, completed={d['completed']}"
        )
        yellow(
            f"    participants={d['total_participants']}, agendas={d['total_agendas']}, resolved={d['resolved_agendas']}"
        )

    return act_id


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════
def main():
    bold("══════════════════════════════════════════════════════════")
    bold("  教研铁三角测试流水注入 — 三条状态机闭环验证")
    bold("══════════════════════════════════════════════════════════")

    # 登录
    cyan("\n[0] 三角色登录...")
    tokens = {}
    uids = {}
    for role in ["admin", "leader", "teacher"]:
        tokens[role], uids[role] = login(role)

    # 1. 集体备课
    plan_id = test_lesson_prep(tokens, uids)

    # 2. 听课评课 — 申诉路径
    obs_id_appeal = None
    if plan_id:
        obs_id_appeal = test_observation_appeal(tokens, uids, plan_id)

    # 3. 听课评课 — 确认路径
    obs_id_confirm = None
    if plan_id:
        obs_id_confirm = test_observation_confirm(tokens, uids, plan_id)

    # 4. 教研活动
    if plan_id:
        test_activities(tokens, uids, plan_id, obs_id_appeal, obs_id_confirm)

    # 总结
    bold("\n══════════════════════════════════════════════════════════")
    green("  ✓ 教研铁三角测试流水注入完成!")
    bold("══════════════════════════════════════════════════════════")
    yellow(f"  教案ID: {plan_id}")
    yellow(f"  听课(申诉路径)ID: {obs_id_appeal}")
    yellow(f"  听课(确认路径)ID: {obs_id_confirm}")
    print()
    print("前端验证地址: https://lijiangschool.online/app/research")
    print("登录账号: admin / grade7_leader / ct_2501 (密码 admin123)")


if __name__ == "__main__":
    main()
