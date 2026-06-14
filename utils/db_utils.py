"""
数据库事务安全工具
提供统一的事务提交/回滚机制，避免数据不一致。
"""
from flask import current_app


def safe_commit():
    """
    Wings 系统核心提交守卫（铁幕级）:
    不再静默吞噬错误！一旦数据库提交失败，立刻抛出 RuntimeError，
    强行阻止后续伪造的 'ok: True' 报文吐给前端。

    用法:
        db.session.add(obj)
        safe_commit()                    # 失败直接抛异常 → Flask 返回 500
        return jsonify({"code": 0, "msg": "操作成功"})

    抛出:
        RuntimeError: 数据库提交失败时抛出
    """
    try:
        from models import db
        db.session.commit()
        return True
    except Exception as e:
        from models import db
        db.session.rollback()
        current_app.logger.critical(
            f"[Database Commit Fatal] 事务强行回滚! 根因: {str(e)}", exc_info=True
        )
        raise RuntimeError(f"Database transaction failed: {str(e)}")


def safe_commit_or_abort(msg="数据保存失败", code=500):
    """
    安全提交，失败时直接终止请求并返回错误响应。

    用法:
        safe_commit_or_abort()
        return jsonify({"code": 0, "msg": "操作成功"})

    注意：调用方必须处理返回值:
        result = safe_commit_or_abort()
        if result is not None:
            return result  # 将 Flask response 返回给客户端
    """
    try:
        from models import db
        db.session.commit()
    except Exception as e:
        from models import db
        db.session.rollback()
        current_app.logger.critical(
            f"[Database Commit Fatal] 事务回滚! {msg}: {str(e)}", exc_info=True
        )
        from flask import jsonify
        return jsonify({"code": code, "msg": msg}), code
    return None  # 成功时返回 None，调用方继续


class db_transaction:
    """
    事务装饰器：包裹整个路由函数，自动提交/回滚。

    用法:
        @app.route("/some/route", methods=["POST"])
        @db_transaction()
        def some_route():
            ...  # 做数据库操作，但不调用 commit()
            return jsonify({"code": 0, "msg": "成功"})

    注意：路由函数内不要手动调用 db.session.commit()，
    装饰器会在函数正常返回后自动提交，异常时自动回滚。
    """
    def __init__(self, commit_on_success=True):
        self.commit_on_success = commit_on_success

    def __call__(self, f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            from models import db
            try:
                result = f(*args, **kwargs)
                if self.commit_on_success:
                    db.session.commit()
                return result
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"事务回滚 [{f.__name__}]: {e}", exc_info=True)
                # 如果返回值是 tuple (response, status_code)，直接返回
                # 否则重新抛出，由全局异常处理器处理
                raise
        return decorated
