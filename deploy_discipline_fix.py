#!/usr/bin/env python3
"""
VNC 一键部署脚本 — 违纪详情 Modal + 账号清理
在服务器 /opt/grade7-new/ 目录执行: python deploy_discipline_fix.py
"""
import os, sys

# 1. 列出疑似测试/非法账号
os.environ.setdefault('DATABASE_URL', 'mysql+pymysql://grade7:waOPKoyFf4ByQD1h@127.0.0.1:3307/grade7_new')
sys.path.insert(0, '/opt/grade7-new')

from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    # 查找疑似测试账号
    suspects = User.query.filter(
        db.or_(
            User.display_name.like('%胡老师%'),
            User.display_name.like('%家长测试%'),
            User.display_name.like('%测试%'),
            User.display_name.like('%胡%'),
            User.username.like('%test%'),
            User.username.like('%hu%'),
        )
    ).all()

    print("=" * 50)
    print("疑似测试/非法账号列表：")
    print("=" * 50)
    for u in suspects:
        print(f"  ID={u.id} | username={u.username} | display_name={u.display_name} | role={u.role} | is_active={u.is_active}")
    print()

    # 软删除匹配"胡老师"和"家长测试"的账号
    deleted = []
    for u in suspects:
        name = (u.display_name or '').strip()
        if '胡老师' in name or '家长测试' in name:
            # 确保不是最后一个管理员
            if u.role == 'ms_admin':
                admin_count = User.query.filter_by(role='ms_admin', is_active=True).count()
                if admin_count <= 1 and u.is_active:
                    print(f"  [SKIP] {u.display_name} 是最后一个管理员，跳过删除")
                    continue

            u.is_active = False
            u.username = f"{u.username}_deleted_{u.id}"
            u.phone = None
            deleted.append(u)
            print(f"  [DELETED] ID={u.id} | {u.display_name} -> username={u.username}")

    if deleted:
        db.session.commit()
        print(f"\n成功软删除 {len(deleted)} 个账号")
    else:
        print("\n未找到匹配'胡老师'或'家长测试'的账号")

    # 列出当前所有活跃用户供确认
    print("\n" + "=" * 50)
    print("当前所有活跃用户：")
    print("=" * 50)
    active_users = User.query.filter_by(is_active=True).order_by(User.id).all()
    for u in active_users:
        print(f"  ID={u.id} | {u.username:20s} | {u.display_name:10s} | {u.role}")
    print(f"\n共 {len(active_users)} 个活跃账号")

    # 2. 确认模板文件存在（手动 git pull 后）
    tmpl_path = '/opt/grade7-new/templates/class_/discipline.html'
    if os.path.exists(tmpl_path):
        with open(tmpl_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'detailModal' in content:
            print(f"\n模板 discipline.html 已包含 detailModal（最新版本）")
        else:
            print(f"\n[WARN] 模板 discipline.html 未包含 detailModal，请先执行 git pull")
    else:
        print(f"\n[WARN] 模板文件不存在: {tmpl_path}")
