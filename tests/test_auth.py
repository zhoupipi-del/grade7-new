"""
test_auth.py — AuthService 核心安全功能测试

覆盖范围：
- bcrypt 密码哈希与验证往返
- SHA-256 旧格式向后兼容
- needs_rehash 迁移检测
- JWT token 生成与解码
- 密码强度规则验证
- change_password 完整流程
"""
import os
import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

# 确保环境变量在 import 前设置
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://fake:fake@127.0.0.1:3307/fake")

from core.services import AuthService


class TestPasswordHashing:
    """bcrypt 密码哈希与验证"""

    def test_hash_password_produces_bcrypt_format(self):
        """哈希结果应以 $2b$ 开头（bcrypt cost=12）"""
        hashed = AuthService.hash_password("TestPass123!")
        assert hashed.startswith("$2b$12$")

    def test_hash_password_is_different_each_time(self):
        """同一密码每次哈希结果不同（salt随机）"""
        h1 = AuthService.hash_password("TestPass123!")
        h2 = AuthService.hash_password("TestPass123!")
        assert h1 != h2

    def test_verify_correct_bcrypt_password(self):
        """正确密码验证通过"""
        hashed = AuthService.hash_password("MySecure456!")
        assert AuthService.verify_password("MySecure456!", hashed) is True

    def test_verify_wrong_bcrypt_password(self):
        """错误密码验证失败"""
        hashed = AuthService.hash_password("MySecure456!")
        assert AuthService.verify_password("WrongPass!", hashed) is False

    def test_verify_empty_password_fails(self):
        """空密码验证失败"""
        hashed = AuthService.hash_password("TestPass123!")
        assert AuthService.verify_password("", hashed) is False


class TestSHA256BackwardCompat:
    """SHA-256 旧格式向后兼容验证"""

    @staticmethod
    def _make_sha256_hash(password: str, salt: str = "somesalt") -> str:
        """构造旧 SHA-256 格式哈希"""
        digest = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256${salt}${digest}"

    def test_verify_correct_sha256_password(self):
        """旧 SHA-256 格式密码验证通过"""
        sha_hash = self._make_sha256_hash("OldPass123!")
        assert AuthService.verify_password("OldPass123!", sha_hash) is True

    def test_verify_wrong_sha256_password(self):
        """旧 SHA-256 格式错误密码验证失败"""
        sha_hash = self._make_sha256_hash("OldPass123!")
        assert AuthService.verify_password("WrongPass!", sha_hash) is False

    def test_verify_sha256_does_not_crash_on_malformed(self):
        """畸形 SHA-256 哈希不崩溃"""
        assert AuthService.verify_password("test", "sha256$badformat") is False


class TestNeedsRehash:
    """旧哈希格式迁移检测"""

    def test_sha256_hash_needs_rehash(self):
        """sha256$ 格式需要重新哈希"""
        assert AuthService.needs_rehash("sha256$salt$hash") is True

    def test_bcrypt_hash_does_not_need_rehash(self):
        """$2b$ 格式不需要重新哈希"""
        bcrypt_hash = AuthService.hash_password("Test123!")
        assert AuthService.needs_rehash(bcrypt_hash) is False

    def test_empty_hash_does_not_need_rehash(self):
        """空哈希不需要重新哈希（边界情况）"""
        assert AuthService.needs_rehash("") is False


class TestJWTToken:
    """JWT token 生成与解码"""

    @staticmethod
    def _make_mock_user():
        return SimpleNamespace(
            id=42,
            username="testuser",
            role="admin",
            school_id=1,
        )

    def test_create_token_returns_string(self):
        """create_token 返回字符串"""
        token = AuthService.create_token(self._make_mock_user())
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_token_returns_correct_payload(self):
        """decode_token 返回正确的 payload"""
        user = self._make_mock_user()
        token = AuthService.create_token(user)
        payload = AuthService.decode_token(token)
        assert payload["sub"] == str(user.id)
        assert payload["username"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["school_id"] == 1

    def test_decode_token_with_invalid_token_raises(self):
        """无效 token 解码应抛异常"""
        from jwt.exceptions import InvalidTokenError
        try:
            AuthService.decode_token("invalid.token.here")
            assert False, "应该抛出异常"
        except InvalidTokenError:
            pass  # 预期行为

    def test_token_contains_iat_and_exp(self):
        """token 包含签发时间和过期时间"""
        token = AuthService.create_token(self._make_mock_user())
        payload = AuthService.decode_token(token)
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_token_expiry_is_24_hours(self):
        """token 过期时间为 24 小时（86400秒）"""
        token = AuthService.create_token(self._make_mock_user())
        payload = AuthService.decode_token(token)
        duration = payload["exp"] - payload["iat"]
        assert duration == 86400


class TestPasswordStrength:
    """密码强度规则验证"""

    def test_password_too_short(self):
        """少于 8 字符的密码被拒绝"""
        error = AuthService.validate_password_strength("Ab1!", "user")
        assert error is not None

    def test_password_too_long(self):
        """超过 128 字符的密码被拒绝"""
        long_pw = "Aa1!" + "x" * 130
        error = AuthService.validate_password_strength(long_pw, "user")
        assert error is not None

    def test_password_contains_username(self):
        """包含用户名的密码被拒绝"""
        error = AuthService.validate_password_strength("testuser123!", "testuser")
        assert error is not None

    def test_password_only_two_categories(self):
        """仅 2 类字符的密码被拒绝（小写+数字）"""
        error = AuthService.validate_password_strength("lowercase1", "user")
        assert error is not None

    def test_password_only_letters(self):
        """纯字母密码被拒绝（大写+小写=2类）"""
        error = AuthService.validate_password_strength("OnlyLetters", "user")
        assert error is not None

    def test_password_valid_four_categories(self):
        """4 类字符的强密码通过验证"""
        error = AuthService.validate_password_strength("ValidPass123!", "user")
        assert error is None

    def test_password_valid_three_categories(self):
        """3 类字符的密码通过验证（大写+小写+数字）"""
        error = AuthService.validate_password_strength("ValidPass123", "user")
        assert error is None


class TestChangePassword:
    """change_password 完整流程测试"""

    @staticmethod
    def _make_mock_db():
        """创建 Mock 数据库会话"""
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @staticmethod
    def _make_user(password: str, username: str = "testuser", change_required: bool = False):
        """创建 Mock 用户对象"""
        return SimpleNamespace(
            password_hash=AuthService.hash_password(password),
            username=username,
            password_change_required=change_required,
        )

    def test_change_password_wrong_old_password(self):
        """旧密码错误时返回失败"""
        user = self._make_user("OldPass123!")
        db = self._make_mock_db()
        success, error = asyncio.run(
            AuthService.change_password(db, user, "WrongOld123!", "NewPass456!")
        )
        assert success is False
        assert error is not None
        assert "原密码" in error

    def test_change_password_success(self):
        """正确旧密码时成功修改"""
        user = self._make_user("OldPass123!", change_required=True)
        db = self._make_mock_db()
        success, error = asyncio.run(
            AuthService.change_password(db, user, "OldPass123!", "NewPass456!")
        )
        assert success is True
        assert error is None
        assert AuthService.verify_password("NewPass456!", user.password_hash) is True
        assert user.password_change_required is False
        db.commit.assert_called_once()

    def test_change_password_same_as_old(self):
        """新密码与旧密码相同时被拒绝"""
        user = self._make_user("OldPass123!")
        db = self._make_mock_db()
        success, error = asyncio.run(
            AuthService.change_password(db, user, "OldPass123!", "OldPass123!")
        )
        assert success is False
        assert error is not None
        assert "相同" in error

    def test_change_password_weak_new_password(self):
        """新密码强度不足时被拒绝"""
        user = self._make_user("OldPass123!")
        db = self._make_mock_db()
        success, error = asyncio.run(
            AuthService.change_password(db, user, "OldPass123!", "weak")
        )
        assert success is False
        assert error is not None
