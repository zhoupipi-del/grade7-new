"""JWT Token 工具 — 小程序 API 认证"""
import jwt
from datetime import datetime, timedelta
from flask import current_app


def create_token(user_id, role, display_name, bound_student_id=None,
                 grade_id=None, class_id=None):
    """生成 JWT token"""
    payload = {
        "user_id": user_id,
        "role": role,
        "display_name": display_name,
        "bound_student_id": bound_student_id,
        "grade_id": grade_id,
        "class_id": class_id,
        "exp": datetime.utcnow() + timedelta(
            hours=current_app.config.get("JWT_EXPIRATION_HOURS", 720)
        ),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )


def verify_token(token):
    """验证 JWT token，返回 payload 或 None"""
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
        )
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def refresh_token(token):
    """刷新 token（若未过期则生成新 token）"""
    payload = verify_token(token)
    if not payload:
        return None
    # 删除过期时间，重新签发
    payload.pop("exp", None)
    payload.pop("iat", None)
    payload["exp"] = datetime.utcnow() + timedelta(
        hours=current_app.config.get("JWT_EXPIRATION_HOURS", 720)
    )
    payload["iat"] = datetime.utcnow()
    return jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
