"""
pytest 测试骨架 —  conftest.py（基石组件）
提供：app、client、logged_in_client 三个核心 fixture
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# 将项目根目录添加到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import session

# 测试环境隔离：使用 SQLite 内存数据库
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def app():
    """创建测试用 Flask app，使用 SQLite 内存数据库"""
    # 必须在导入 app 之前设置环境变量
    os.environ.update({
        "FLASK_ENV": "testing",
        "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
        "JWT_SECRET_KEY": "test-jwt-secret-32-chars-minimum!!",
        "DATABASE_URL": TEST_DATABASE_URL,
        "LLM_API_KEY": "test-key",
        "LLM_API_URL": "https://api.test.com",
        "LLM_MODEL": "test-model"
    })

    from app import create_app, db
    from sqlalchemy import inspect

    test_app = create_app()
    test_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
        "SQLALCHEMY_ENGINE_OPTIONS": {},  # SQLite 不需要连接池参数
        "WTF_CSRF_ENABLED": False
    })

    with test_app.app_context():
        # 创建所有表
        db.create_all()
        yield test_app
        # 测试结束后销毁
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """提供未登录的测试客户端"""
    return app.test_client()


@pytest.fixture(scope="function")
def logged_in_client(app):
    """提供已登录的测试客户端（ms_admin 角色）"""
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "ms_admin"
        sess["display_name"] = "Test Admin"
        sess["grade_id"] = 1
        sess["class_id"] = 1

    return client


@pytest.fixture(scope="function")
def logged_in_teacher(app):
    """提供已登录的测试客户端（class_teacher 角色）"""
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user_id"] = 2
        sess["username"] = "teacher"
        sess["role"] = "class_teacher"
        sess["display_name"] = "Test Teacher"
        sess["grade_id"] = 1
        sess["class_id"] = 1

    return client


@pytest.fixture(scope="function")
def logged_in_parent(app):
    """提供已登录的测试客户端（parent 角色）"""
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user_id"] = 3
        sess["username"] = "parent"
        sess["role"] = "parent"
        sess["display_name"] = "Test Parent"
        sess["grade_id"] = 1
        sess["class_id"] = 1

    return client
