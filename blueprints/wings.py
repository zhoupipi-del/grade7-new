"""五翼评价 → 综合素质评价 兼容重定向（Phase 3 五翼合流）

本蓝图已降级为纯重定向层。所有旧 Wings URL 自动 302 跳转到
对应的 Quality（综合素质评价）页面，确保用户书签和外部链接不中断。

迁移完成后（Phase 3 收尾）本蓝图可安全删除。
"""

from flask import Blueprint, redirect, url_for, jsonify, request

wings_bp = Blueprint("wings", __name__)

# ── Wings → Quality URL 映射表 ──
# 注意：使用 lambda 延迟求值，避免 url_for 在蓝图注册前执行
REDIRECT_MAP = {
    "/":                 lambda: url_for("quality.dashboard"),
    "/score":            lambda: url_for("quality.score"),
    "/score/teacher":    lambda: url_for("quality.score"),
    "/score/parent":     lambda: url_for("quality.score"),
    "/score/student":    lambda: url_for("quality.self_eval"),
    "/class-ranking":    lambda: url_for("quality.class_overview"),
    "/medals":           lambda: url_for("quality.dashboard"),
    "/portfolio":        lambda: url_for("quality.dashboard"),
    "/analysis":         lambda: url_for("quality.overview"),
}


@wings_bp.route("/", defaults={"path": ""})
@wings_bp.route("/<path:path>")
def wings_redirect(path):
    """统一重定向入口 — 将旧 Wings 路径映射到 Quality 路径"""

    # API 端点直接返回 410 Gone
    if path.startswith("api/"):
        return jsonify({
            "error": "GONE",
            "message": "五翼评价已合流至综合素质评价模块，请访问 /quality/",
            "migrated_to": "/quality/",
        }), 410

    # 参数化路由：/portfolio/<sid> → /quality/report/<sid>
    if path.startswith("portfolio/") and path.split("/")[-1].isdigit():
        sid = int(path.split("/")[-1])
        return redirect(url_for("quality.report", sid=sid), code=302)

    # 查映射表
    route_key = "/" + path if path else "/"
    redirect_fn = REDIRECT_MAP.get(route_key)

    if redirect_fn:
        return redirect(redirect_fn(), code=302)

    # 未匹配的旧路径 → 兜底到 Quality Dashboard
    return redirect(url_for("quality.dashboard"), code=302)
