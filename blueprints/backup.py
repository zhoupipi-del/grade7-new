"""数据备份与恢复 — 仅德育处管理员可用"""
import os
import re
import subprocess
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app
from sqlalchemy import text
from models import db
from decorators import require_role
from utils.db_utils import safe_commit

backup_bp = Blueprint("backup", __name__)

BACKUP_DIR = "backups"


def _get_backup_path():
    return os.path.join(current_app.root_path, BACKUP_DIR)


def _parse_db_url(db_url):
    """从 DATABASE_URL 解析 MySQL 连接参数"""
    # mysql+pymysql://user:pass@host:port/dbname
    m = re.match(
        r"mysql(?:\+pymysql)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
        db_url,
    )
    if m:
        return {
            "user": m.group(1),
            "password": m.group(2),
            "host": m.group(3),
            "port": m.group(4),
            "database": m.group(5),
        }
    return None


def _get_db_info():
    """获取数据库基本信息"""
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    info = _parse_db_url(db_url)
    if info:
        try:
            tables = int(db.session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :s"),
                {"s": info["database"]},
            ).scalar() or 0)
            total_rows = db.session.execute(
                text(
                    "SELECT SUM(table_rows) FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_type = 'BASE TABLE'"
                ),
                {"s": info["database"]},
            ).scalar()
            db_size = db.session.execute(
                text(
                    "SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) "
                    "FROM information_schema.tables WHERE table_schema = :s"
                ),
                {"s": info["database"]},
            ).scalar()
            return {
                "engine": "MySQL",
                "database": info["database"],
                "host": info["host"],
                "table_count": tables,
                "total_records": int(total_rows or 0),
                "db_size_mb": float(db_size or 0),
            }
        except Exception:
            return {
                "engine": "MySQL",
                "database": info.get("database", "未知"),
                "host": info.get("host", "未知"),
                "table_count": 0,
                "total_records": 0,
                "db_size_mb": 0,
            }

    # SQLite fallback
    db_path = current_app.config.get("SQLALCHEMY_DATABASE_URI", "").replace("sqlite:///", "")
    if db_path and not db_path.startswith("sqlite"):
        try:
            size_mb = os.path.getsize(db_path) / 1024 / 1024
            tables = int(db.session.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")).scalar() or 0)
            return {
                "engine": "SQLite",
                "database": os.path.basename(db_path),
                "host": "本地文件",
                "table_count": tables or 0,
                "total_records": 0,
                "db_size_mb": round(size_mb, 2),
            }
        except Exception:
            pass

    return {"engine": "未知", "database": "未知", "host": "未知", "table_count": 0, "total_records": 0, "db_size_mb": 0}


def _list_backups():
    """列出备份目录中的 .sql 文件"""
    bp = _get_backup_path()
    os.makedirs(bp, exist_ok=True)
    backups = []
    for fname in sorted(os.listdir(bp), reverse=True):
        if fname.endswith(".sql"):
            fpath = os.path.join(bp, fname)
            stat = os.stat(fpath)
            backups.append({
                "filename": fname,
                "size_kb": round(stat.st_size / 1024, 1),
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    return backups


# ── 备份管理首页 ──
@backup_bp.route("/")
@require_role("ms_admin")
def dashboard():
    backups = _list_backups()
    db_info = _get_db_info()
    return render_template("backup/dashboard.html", backups=backups, db_info=db_info)


# ── 创建备份 ──
@backup_bp.route("/create", methods=["POST"])
@require_role("ms_admin")
def create_backup():
    bp = _get_backup_path()
    os.makedirs(bp, exist_ok=True)

    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    info = _parse_db_url(db_url)

    if not info:
        flash("仅支持 MySQL 数据库备份（当前为 SQLite）", "danger")
        return redirect(url_for("backup.dashboard"))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.sql"
    filepath = os.path.join(bp, filename)

    try:
        cmd = [
            "mysqldump",
            f"-h{info['host']}",
            f"-P{info['port']}",
            f"-u{info['user']}",
            f"-p{info['password']}",
            "--single-transaction",
            "--routines",
            "--triggers",
            info["database"],
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=300)
            if result.returncode != 0:
                os.remove(filepath)
                flash(f"备份失败: {result.stderr.decode('utf-8', errors='replace')}", "danger")
                return redirect(url_for("backup.dashboard"))

        file_size = os.path.getsize(filepath)
        flash(f"备份成功: {filename}（{round(file_size / 1024, 1)} KB）", "success")
    except FileNotFoundError:
        flash("mysqldump 命令不存在，请先安装 MySQL 客户端工具", "danger")
    except subprocess.TimeoutExpired:
        flash("备份超时（超过5分钟），数据库可能过大", "danger")
    except Exception as e:
        flash(f"备份异常: {str(e)}", "danger")

    return redirect(url_for("backup.dashboard"))


# ── 下载备份 ──
@backup_bp.route("/download/<filename>")
@require_role("ms_admin")
def download_backup(filename):
    bp = _get_backup_path()
    if not os.path.isfile(os.path.join(bp, filename)):
        flash("文件不存在", "danger")
        return redirect(url_for("backup.dashboard"))
    return send_from_directory(bp, filename, as_attachment=True)


# ── 恢复备份 ──
@backup_bp.route("/restore", methods=["POST"])
@require_role("ms_admin")
def restore_backup():
    uploaded = request.files.get("sql_file")
    if not uploaded or not uploaded.filename.endswith(".sql"):
        flash("请上传 .sql 备份文件", "warning")
        return redirect(url_for("backup.dashboard"))

    sql_content = uploaded.read().decode("utf-8", errors="replace")
    if len(sql_content) < 10:
        flash("备份文件内容为空", "danger")
        return redirect(url_for("backup.dashboard"))

    # ── 安全校验：检测破坏性 SQL 语句 ──
    DANGEROUS_KEYWORDS = [
        "DROP ", "DROP\n", "DROP\t", "DROP\r",
        "DELETE FROM", "DELETE\nFROM", "DELETE\tFROM",
        "TRUNCATE ", "TRUNCATE\n", "TRUNCATE\t",
        "ALTER TABLE", "ALTER\nTABLE", "ALTER\tTABLE",
        "UPDATE ", "UPDATE\n", "UPDATE\t",
    ]
    sql_upper = sql_content.upper()
    for kw in DANGEROUS_KEYWORDS:
        if kw in sql_upper:
            kw_clean = kw.replace("\n", " ").replace("\t", " ").replace("\r", " ").strip()
            current_app.logger.warning(
                f"备份恢复被拒绝: 文件含破坏性语句 '{kw_clean}' "
                f"操作人={session.get('username')}"
            )
            flash(f"安全检查: 备份文件含破坏性语句 ({kw_clean})，还原已拒绝", "danger")
            return redirect(url_for("backup.dashboard"))

    try:
        # 将 SQL 按语句拆分并逐条执行
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]
        executed = 0
        errors = []
        for stmt in statements:
            if stmt:
                try:
                    db.session.execute(text(stmt))
                    executed += 1
                except Exception as e:
                    # 忽略 mysqldump 产生的注释/头部警告等
                    err_str = str(e).lower()
                    if "duplicate" in err_str or "already exists" in err_str:
                        continue
                    errors.append(str(e))
        safe_commit()
        if errors:
            flash(f"恢复完成: 执行 {executed} 条，{len(errors)} 条错误", "warning")
        else:
            flash(f"恢复成功: 共执行 {executed} 条 SQL 语句", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"恢复失败: {str(e)}", "danger")

    return redirect(url_for("backup.dashboard"))


# ── 删除备份 ──
@backup_bp.route("/<filename>/delete", methods=["POST"])
@require_role("ms_admin")
def delete_backup(filename):
    bp = _get_backup_path()
    fpath = os.path.join(bp, filename)
    # 防止路径遍历
    if not filename.endswith(".sql") or ".." in filename or "/" in filename:
        flash("非法文件名", "danger")
        return redirect(url_for("backup.dashboard"))
    if os.path.isfile(fpath):
        os.remove(fpath)
        flash(f"已删除: {filename}", "success")
    else:
        flash("文件不存在", "danger")
    return redirect(url_for("backup.dashboard"))
