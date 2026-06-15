#!/usr/bin/env python3
"""
批量录入年级组违纪记录 — 2026年4-6月
直接连接数据库，不走 Flask 应用（避免 Config 校验问题）
created_by = 2 (grade7_leader)
"""
import sys
from datetime import date, datetime
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new"
CREATED_BY = 2  # grade7_leader

# ── 学生ID映射（用户提供的名字 → 数据库中的名字和ID） ──
STUDENTS = {
    # 2501班
    "毛佳睿":  (25, 1, 1),
    "叶梓豪":  (390, 1, 1),   # 用户写"叶子豪"
    "汤志翔":  (32, 1, 1),
    # 2502班
    "陈佳乐":  (53, 2, 1),
    "柳妍熙":  (76, 2, 1),   # 用户写"柳研熙"
    "罗炎旺":  (79, 2, 1),
    "李旭尧":  (69, 2, 1),
    "李君豪":  (67, 2, 1),
    "曾宇晗":  (50, 2, 1),   # 用户写"曾宇涵"
    "刘煜泽":  (74, 2, 1),
    "胡锁":    (63, 2, 1),
    "夏文轩":  (89, 2, 1),
    "戴诗颖":  (56, 2, 1),
    "吴书研":  (88, 2, 1),   # 用户写"吴淑研"
    # 2503班
    "肖湘轩":  (137, 3, 1),
    # 2504班
    "阳鑫":    (183, 4, 1),  # 用户写"杨鑫"
    "杨新志":  (185, 4, 1),  # 用户写"杨星志"
}

# ── 违纪记录列表 ──
# 格式: (日期, [(学生DB名字, 学生ID, class_id, grade_id), ...], 类别, 描述)
VIOLATIONS = [
    # 1. 5月12日 2502班柳研熙，陈佳乐 课后服务不进教室
    (date(2026, 5, 12), ["柳妍熙", "陈佳乐"], "课堂",
     "课后服务不进教室"),

    # 2. 5月12日 2502班陈佳乐，柳研熙 眼保健操串班
    (date(2026, 5, 12), ["陈佳乐", "柳妍熙"], "两操",
     "眼保健操串班"),

    # 3. 5月20日 2502班罗炎旺，李旭尧，李君豪，曾宇涵 课间操旷操
    (date(2026, 5, 20), ["罗炎旺", "李旭尧", "李君豪", "曾宇晗"], "两操",
     "课间操旷操"),

    # 4. 6月3日 刘煜泽 带电子烟
    (date(2026, 6, 3), ["刘煜泽"], "吸烟",
     "带电子烟"),

    # 5. 6月11日 2504班杨鑫，杨星志 逃课在外面玩
    (date(2026, 6, 11), ["阳鑫", "杨新志"], "课堂",
     "逃课在外面玩"),

    # 6. 6月10日 2504班杨鑫，杨星志 逃课在外面玩
    (date(2026, 6, 10), ["阳鑫", "杨新志"], "课堂",
     "逃课在外面玩"),

    # 7. 6月15日 2502班柳研熙，胡锁 + 2504班杨鑫，杨星志 课间操躲着不跑
    (date(2026, 6, 15), ["柳妍熙", "胡锁", "阳鑫", "杨新志"], "两操",
     "课间操躲着不跑"),

    # 8. 4月28日 2502班陈佳乐 敲诈2504班的一名同学
    (date(2026, 4, 28), ["陈佳乐"], "打架",
     "敲诈2504班的一名同学"),

    # 9. 4月15日 2501班叶子豪 顶撞语文老师
    (date(2026, 4, 15), ["叶梓豪"], "课堂",
     "顶撞语文老师"),

    # 10. 4月8日 2501班毛佳睿 带初二姐姐来初一校园霸凌; 2503班肖湘轩,2502班夏文轩参与
    (date(2026, 4, 8), ["毛佳睿"], "打架",
     "带着初二的姐姐来初一这里校园霸凌同学"),
    (date(2026, 4, 8), ["肖湘轩"], "打架",
     "在旁边参与校园霸凌"),
    (date(2026, 4, 8), ["夏文轩"], "打架",
     "在旁边参与校园霸凌"),

    # 11. 5月14日 2502班柳研熙，戴诗颖，陈佳乐，胡锁，吴淑研 多次打上课铃未进教室
    (date(2026, 5, 14), ["柳妍熙", "戴诗颖", "陈佳乐", "胡锁", "吴书研"], "迟到",
     "多次打上课铃还未进教室，在外闲逛"),

    # 12. 5月13日 2502班夏文轩 多次逃课
    (date(2026, 5, 13), ["夏文轩"], "课堂",
     "多次逃课，不上课，在外面玩"),

    # 13. 6月10日 2501班叶子豪，汤志翔 多次逃课
    (date(2026, 6, 10), ["叶梓豪", "汤志翔"], "课堂",
     "多次逃课不上课，在外面玩"),
]

def main():
    engine = create_engine(DB_URL, pool_pre_ping=True)

    # 先验证所有学生存在
    with engine.connect() as conn:
        all_names = set()
        for _, names, _, _ in VIOLATIONS:
            all_names.update(names)

        not_found = []
        for name in all_names:
            if name not in STUDENTS:
                not_found.append(name)

        if not_found:
            print(f"[ERROR] 以下学生在STUDENTS映射中不存在: {not_found}")
            sys.exit(1)

        print(f"[OK] 共 {len(all_names)} 名学生，{len(VIOLATIONS)} 条违纪事件")
        total_records = sum(len(names) for _, names, _, _ in VIOLATIONS)
        print(f"[OK] 预计生成 {total_records} 条违纪记录")

        # 确认操作
        print("\n即将插入以下记录:")
        for vdate, names, cat, desc in VIOLATIONS:
            print(f"  {vdate} | {cat} | {desc} | 学生: {', '.join(names)}")
        print(f"\n总计: {total_records} 条 | type=warning | points=-10 | created_by=grade7_leader")

        # 逐条插入
        inserted = 0
        errors = []
        for vdate, names, cat, desc in VIOLATIONS:
            for name in names:
                sid, cid, gid = STUDENTS[name]
                created_at = datetime.combine(vdate, datetime.min.time().replace(hour=10, minute=0))
                try:
                    conn.execute(
                        text("""INSERT INTO discipline_records
                               (student_id, class_id, grade_id, type, category, description,
                                action_taken, points, status, verify_status, created_by, created_at)
                               VALUES
                               (:sid, :cid, :gid, :type, :cat, :desc, :action, :pts, :status, :verify, :by, :at)"""),
                        {
                            "sid": sid, "cid": cid, "gid": gid,
                            "type": "warning",
                            "cat": cat,
                            "desc": desc,
                            "action": "警告处分，扣10分",
                            "pts": 10,
                            "status": "active",
                            "verify": "VERIFIED",
                            "by": CREATED_BY,
                            "at": created_at,
                        }
                    )
                    inserted += 1
                except Exception as e:
                    errors.append(f"  {name}({vdate}): {e}")

        conn.commit()

        print(f"\n{'='*50}")
        print(f"[DONE] 成功插入 {inserted} 条违纪记录")
        if errors:
            print(f"[ERROR] {len(errors)} 条失败:")
            for e in errors:
                print(e)
        else:
            print("[OK] 全部成功，无错误")

if __name__ == "__main__":
    main()
