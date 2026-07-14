"""
心理咨询预约与工作台 模块清单
模块加载器通过此文件注册路由

隐私声明:
  psy_consult_records.encrypted_clog 使用 Fernet 对称加密,
  解密密钥从环境变量 PSY_ENCRYPTION_KEY 或 WINGS_ENCRYPTION_KEY 加载。
  生产环境必须手动注入强随机密钥。
"""

MODULE_CODE = "psych_counseling"
MODULE_NAME = "心理咨询预约与工作台"
MODULE_CATEGORY = "wellness"
MODULE_DEPENDENCIES = ["teacher_mgmt"]  # 依赖 teacher_role_assignments 中的 counselor 角色
ENABLED_BY_DEFAULT = False  # 敏感模块, 需手动启用

MODULE_PHASES = ["junior", "senior", "primary", "integrated"]


def register(router_prefix="/api/v1/psych-counseling"):
    from modules.psych_counseling.routers import router

    return router, router_prefix
