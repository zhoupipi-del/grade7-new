#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
问卷数据完整导入脚本 v2
==========================================
改进：
  - 预加载全量学生到内存 dict，O(1) 查找
  - 支持姓名模糊匹配（去掉空格/全角→半角）
  - 导入 MSSMHS-55（363条）+ PCE-55（341条）
  - 自动计算10维度分 → 写 dimensions_json
  - 高风险 → risk_records + problem_students

用法：python import_survey_full_v2.py
"""

import json, os, sys, pymysql, re
from datetime import date, datetime
from collections import defaultdict

# ── 数据库配置 ──────────────────────────────────
DB = dict(
    host="127.0.0.1", port=13306,
    user="grade7", password="waOPKoyFf4ByQD1h",
    database="grade7_new", charset="utf8mb4"
)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FILE_MS  = os.path.join(BASE_DIR, "psych_answers_cleaned.json")
FILE_PCE = os.path.join(BASE_DIR, "parent_answers_cleaned.json")

# ── MSSMHS-55 维度定义 ───────────────────────────
DIMENSIONS = [
    "强迫症状", "偏执", "敌对", "人际敏感", "抑郁",
    "焦虑", "学习压力", "适应不良", "情绪不平衡", "心理不平衡",
]
# 题号 → 维度索引（原题号 1~55）
Q_TO_DIM = {}
_dim_lists = [
    [1,11,21,31,41,51],        # 0: 强迫症状
    [2,12,22,32,42,52],        # 1: 偏执
    [3,13,23,33,43,53],        # 2: 敌对
    [4,14,24,34,44,54],        # 3: 人际敏感
    [5,15,25,35,45,55],        # 4: 抑郁
    [6,16,26,36,46],            # 5: 焦虑
    [7,17,27,37,47],            # 6: 学习压力
    [8,18,28,38,48],            # 7: 适应不良
    [9,19,29,39,49],            # 8: 情绪不平衡
    [10,20,30,40,50],          # 9: 心理不平衡
]
for dim_idx, q_list in enumerate(_dim_lists):
    for q in q_list:
        Q_TO_DIM[q] = dim_idx

OPT_SCORE = {"从无": 1, "轻度": 2, "中度": 3, "偏重": 4}

# ── 工具函数 ──────────────────────────────────────
def log(msg):
    print(f"  {msg}", flush=True)


def build_student_map(conn):
    """
    预加载全量学生 → 返回三层 dict：
      stu_map[姓名规范][班级名][班级名] = {id, class_id, grade_id}
    姓名规范：去掉空格、全角→半角、转为统一格式
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.name, s.student_no,
               c.name AS class_name, c.id AS class_id,
               g.name AS grade_name, g.id AS grade_id
        FROM students s
        JOIN classes c ON s.class_id = c.id
        JOIN grades g ON s.grade_id = g.id
        WHERE s.is_active = 1
    """)
    rows = cur.fetchall()
    cur.close()

    # 多层索引：norm_name -> class_name -> student_info
    stu_map = defaultdict(lambda: defaultdict(list))
    for row in rows:
        sid, name, sno, cname, cid, gname, gid = row
        norm = normalize_name(name)
        info = {
            "id": sid, "name": name,
            "student_no": sno,
            "class_name": cname, "class_id": cid,
            "grade_name": gname, "grade_id": gid,
        }
        stu_map[norm][cname].append(info)
    return stu_map


def normalize_name(name):
    """姓名规范化：去空格、全角数字→半角"""
    if not name:
        return ""
    name = name.strip()
    # 全角→半角
    name = name.replace("（", "(").replace("）", ")")
    name = re.sub(r"[\s\-_]+", "", name)
    return name


def find_student(stu_map, name, class_name=None):
    """
    在学生 map 中查找，返回 student_info dict 或 None
    匹配策略：
      1. 精确匹配 name+class
      2. 尝试给 class_name 加"班"后缀再匹配
      3. 仅 name 匹配（唯一时）
    """
    norm = normalize_name(name)
    if norm not in stu_map:
        return None
    by_class = stu_map[norm]

    # 1. 精确匹配
    if class_name and class_name in by_class:
        lst = by_class[class_name]
        return lst[0] if lst else None

    # 2. 尝试加"班"后缀
    if class_name:
        class_with_ban = class_name + "班"
        if class_with_ban in by_class:
            lst = by_class[class_with_ban]
            return lst[0] if lst else None

        # 3. 尝试去掉"班"后缀
        if class_name.endswith("班"):
            class_no_ban = class_name[:-1]
            if class_no_ban in by_class:
                lst = by_class[class_no_ban]
                return lst[0] if lst else None

    # 4. 不指定班级，且唯一
    all_stus = []
    for cls, slist in by_class.items():
        all_stus.extend(slist)
    if len(all_stus) == 1:
        return all_stus[0]
    return None


def extract_ms_scores(answer_item):
    """从单条回答提取55题分值，返回 list[55个int]"""
    questions = []
    for page in answer_item.get("answer", []):
        questions.extend(page.get("questions", []))

    scores = []
    for q_idx in range(3, 58):   # Q1~Q55
        if q_idx >= len(questions):
            scores.append(1)
            continue
        q = questions[q_idx]
        val = 1
        for opt in q.get("options", []):
            if opt.get("checked") == 1:
                txt = opt.get("text", "从无")
                val = OPT_SCORE.get(txt, 1)
                break
        scores.append(val)
    return scores


def calc_dimensions(scores_55):
    """计算十维度分，返回 (dims_list[10], lie_score, total_score)"""
    dims = [0] * 10
    for q_num, dim_idx in Q_TO_DIM.items():
        idx = q_num - 1
        if 0 <= idx < 55:
            dims[dim_idx] += scores_55[idx]
    lie_score = sum(scores_55[q-2] for q in [8,18,28,38,48] if 0 <= q-2 < 55)
    total = sum(scores_55)
    return dims, lie_score, total


def risk_level(total):
    if total >= 160:
        return "high"
    elif total >= 120:
        return "medium"
    else:
        return "low"


# ── 主流程 ──────────────────────────────────────
def main():
    print("=" * 60)
    print("  问卷数据完整导入脚本 v2")
    print("=" * 60)

    # 1. 连接数据库
    print("\n[1/5] 连接数据库...")
    conn = pymysql.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()
    log("✓ 连接成功")

    # 2. 预加载学生
    print("\n[2/5] 预加载学生名单...")
    stu_map = build_student_map(conn)
    total_stus = sum(len(ss) for dc in stu_map.values() for ss in dc.values())
    log(f"✓ 已加载 {total_stus} 名学生")

    try:
        # ── 3. 清空原有数据 ───────────────────────────
        print("\n[3/5] 清空原有数据...")
        for survey_type in ("MSSMHS-55", "PCE-55"):
            cur.execute(
                "DELETE FROM psych_surveys WHERE survey_type=%s",
                (survey_type,)
            )
            log(f"  psych_surveys({survey_type}): 删除 {cur.rowcount} 条")

        cur.execute(
            """DELETE mha FROM mental_health_assessments mha
               WHERE mha.scale_name='MSSMHS-55'
                 AND mha.assessment_type='questionnaire'"""
        )
        log(f"  mental_health_assessments(MSSMHS-55): 删除 {cur.rowcount} 条")

        cur.execute(
            """DELETE rr FROM risk_records rr
               WHERE rr.warning_details LIKE '%MSSMHS%'"""
        )
        log(f"  risk_records(MSSMHS): 删除 {cur.rowcount} 条")

        conn.commit()
        print("  ✓ 清空完成\n")

        # ── 4. 导入 MSSMHS-55 ───────────────────────────
        print("[4/5] 导入 MSSMHS-55（心理健康筛查）...")
        if not os.path.exists(FILE_MS):
            print(f"  ✗ 文件不存在: {FILE_MS}")
            sys.exit(1)

        with open(FILE_MS, "r", encoding="utf-8") as f:
            ms_data = json.load(f)
        ms_list = ms_data.get("list", [])
        print(f"  读取 {len(ms_list)} 条回答")

        imported_ms = 0
        skipped_ms  = 0
        high_risk_count = 0
        medium_risk_count = 0

        for ans in ms_list:
            questions = []
            for page in ans.get("answer", []):
                questions.extend(page.get("questions", []))

            stu_name    = (questions[0].get("text") or "").strip() if len(questions) > 0 else ""
            class_name  = (questions[1].get("text") or "").strip() if len(questions) > 1 else ""

            if not stu_name:
                skipped_ms += 1
                continue

            stu = find_student(stu_map, stu_name, class_name)
            if not stu:
                log(f"  ⚠ 未找到学生: {stu_name}（班级={class_name}）")
                skipped_ms += 1
                continue

            # 提取分值 + 计算维度
            scores = extract_ms_scores(ans)
            dims, lie_score, total = calc_dimensions(scores)
            risk = risk_level(total)

            answers_json = json.dumps(
                {"scores": scores, "questions_55": True},
                ensure_ascii=False
            )
            dimensions_json = json.dumps(
                {
                    "dimensions": dict(zip(DIMENSIONS, dims)),
                    "lie_score": lie_score,
                    "risk_level": risk
                },
                ensure_ascii=False
            )
            completed_at = ans.get("ended_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 插入 psych_surveys
            cur.execute(
                """INSERT INTO psych_surveys
                   (student_id, class_id, grade_id,
                    survey_type, answers_json, total_score,
                    dimensions_json, is_valid,
                    completed_at, verify_status)
                   VALUES (%s, %s, %s,
                           'MSSMHS-55', %s, %s,
                           %s, 1,
                           %s, 'COMPLETED')""",
                (stu["id"], stu["class_id"], stu["grade_id"],
                 answers_json, total,
                 dimensions_json, completed_at)
            )
            survey_id = cur.lastrowid

            # 插入 mental_health_assessments
            dim_scores_json = json.dumps(
                dict(zip(DIMENSIONS, dims)),
                ensure_ascii=False
            )
            risk_label = {"high": "高风险", "medium": "中风险", "low": "低风险"}[risk]
            conclusion = f"MSSMHS-55心理健康筛查总分{total}，评定为{risk_label}"

            cur.execute(
                """INSERT INTO mental_health_assessments
                   (student_id, class_id, grade_id,
                    assessment_type, scale_name,
                    assessment_date, total_score, risk_level,
                    dimension_scores, conclusion,
                    need_intervention, intervention_plan,
                    assessed_by, status,
                    created_at, updated_at)
                   VALUES (%s, %s, %s,
                           'questionnaire', 'MSSMHS-55',
                           %s, %s, %s,
                           %s, %s,
                           %s, %s,
                           1, 'draft',
                           NOW(), NOW())""",
                (stu["id"], stu["class_id"], stu["grade_id"],
                 date.today(), total, risk,
                 dim_scores_json, conclusion,
                 risk in ("high", "medium"),
                 "由班主任持续关注，心理老师定期回访" if risk == "high" else None)
            )

            # 中高风险 → 写入 risk_records + problem_students
            if risk in ("high", "medium"):
                if risk == "high":
                    high_risk_count += 1
                else:
                    medium_risk_count += 1
                warning_details = [
                    {"type": "MSSMHS-55", "dimension": DIMENSIONS[i], "score": dims[i]}
                    for i in range(10) if dims[i] >= 18
                ]
                cur.execute(
                    """INSERT INTO risk_records
                       (student_id, grade_id, class_id,
                        scan_date, risk_level,
                        warning_details, warning_count,
                        notification_sent, is_processed,
                        created_at, risk_probability)
                       VALUES (%s, %s, %s,
                               %s, %s,
                               %s, %s,
                               0, 0,
                               NOW(), %s)""",
                    (stu["id"], stu["grade_id"], stu["class_id"],
                     date.today(), risk,
                     json.dumps(warning_details, ensure_ascii=False),
                     len(warning_details),
                     0.85 if total >= 180 else (0.70 if total >= 160 else 0.50))
                )

                # problem_students 幂等
                cur.execute(
                    """SELECT id FROM problem_students
                       WHERE student_id=%s AND status='active'
                       LIMIT 1""",
                    (stu["id"],)
                )
                if not cur.fetchone():
                    level = "red" if risk == "high" else "yellow"
                    cur.execute(
                        """INSERT INTO problem_students
                           (student_id, class_id, grade_id,
                            category, level, description,
                            status, created_by, created_at, updated_at)
                           VALUES (%s, %s, %s,
                                   '心理健康', %s,
                                   %s,
                                   'active', 1, NOW(), NOW())""",
                        (stu["id"], stu["class_id"], stu["grade_id"],
                         level, conclusion)
                    )

            imported_ms += 1
            if imported_ms % 50 == 0:
                log(f"  已处理 {imported_ms}/{len(ms_list)}...")

        conn.commit()
        print(f"  ✓ MSSMHS-55 导入完成：成功 {imported_ms}，跳过 {skipped_ms}")
        print(f"    高风险 {high_risk_count} 人，中风险 {medium_risk_count} 人")
        print(f"    已写入 risk_records + problem_students\n")

        # ── 5. 导入 PCE-55 ─────────────────────────────
        print("[5/5] 导入 PCE-55（家长综合测评）...")
        if not os.path.exists(FILE_PCE):
            print(f"  ⚠ 文件不存在，跳过: {FILE_PCE}")
        else:
            with open(FILE_PCE, "r", encoding="utf-8") as f:
                pce_data = json.load(f)
            pce_list = pce_data.get("list", [])
            print(f"  读取 {len(pce_list)} 条回答")

            imported_pce = 0
            skipped_pce  = 0

            for ans in pce_list:
                questions = []
                for page in ans.get("answer", []):
                    questions.extend(page.get("questions", []))

                stu_name   = (questions[0].get("text") or "").strip() if len(questions) > 0 else ""
                class_name = (questions[1].get("text") or "").strip() if len(questions) > 1 else ""

                if not stu_name:
                    skipped_pce += 1
                    continue

                stu = find_student(stu_map, stu_name, class_name)
                if not stu:
                    log(f"  ⚠ 未找到学生: {stu_name}（班级={class_name}）")
                    skipped_pce += 1
                    continue

                # PCE-55 暂不计算维度，仅存储原始 answers_json
                pce_scores = []
                for q_idx in range(3, max(58, len(questions))):
                    if q_idx >= len(questions):
                        break
                    q = questions[q_idx]
                    val = 1
                    for opt in q.get("options", []):
                        if opt.get("checked") == 1:
                            txt = opt.get("text", "从无")
                            val = OPT_SCORE.get(txt, 1)
                            break
                    pce_scores.append(val)

                total = sum(pce_scores)
                answers_json = json.dumps(
                    {"scores": pce_scores, "questions_55": True},
                    ensure_ascii=False
                )
                completed_at = ans.get("ended_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cur.execute(
                    """INSERT INTO psych_surveys
                       (student_id, class_id, grade_id,
                        survey_type, answers_json, total_score,
                        is_valid, completed_at, verify_status)
                       VALUES (%s, %s, %s,
                               'PCE-55', %s, %s,
                               1, %s, 'COMPLETED')""",
                    (stu["id"], stu["class_id"], stu["grade_id"],
                     answers_json, total,
                     completed_at)
                )
                imported_pce += 1
                if imported_pce % 50 == 0:
                    log(f"  已处理 {imported_pce}/{len(pce_list)}...")

            conn.commit()
            print(f"  ✓ PCE-55 导入完成：成功 {imported_pce}，跳过 {skipped_pce}\n")

        # ── 6. 验证结果 ─────────────────────────────
        print("\n[验证] 导入结果统计...")
        for tbl, cond in [
            ("psych_surveys",        "survey_type='MSSMHS-55'"),
            ("psych_surveys",        "survey_type='PCE-55'"),
            ("mental_health_assessments", "scale_name='MSSMHS-55'"),
            ("risk_records",         "risk_level='high'"),
            ("problem_students",     "status='active'"),
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {cond}")
            cnt = cur.fetchone()[0]
            print(f"  {tbl} ({cond}): {cnt} 条")

        cur.close()
        conn.close()

        print("\n" + "=" * 60)
        print("  ✓ 全部导入完成！")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        try:
            cur.close()
        except:
            pass
        conn.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
