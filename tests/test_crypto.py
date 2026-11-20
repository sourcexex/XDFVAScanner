"""Tests for crypto utilities."""

from xdflib.crypto import aes_encrypt, compute_sdk_sign, hmac_sha1_sign


class TestAES:
    def test_encrypt_produces_base64(self):
        result = aes_encrypt("hello", "a" * 16 + "b" * 16)
        assert isinstance(result, str)
        assert len(result) > 0
        # 应该看起来像 Base64
        import base64

        base64.b64decode(result)  # 不应抛出异常

    def test_encrypt_deterministic(self):
        key = "a" * 16 + "b" * 16
        r1 = aes_encrypt("hello", key)
        r2 = aes_encrypt("hello", key)
        assert r1 == r2


class TestHMAC:
    def test_sign_produces_base64(self):
        result = hmac_sha1_sign("test data", "secret")
        import base64

        base64.b64decode(result)

    def test_sign_deterministic(self):
        r1 = hmac_sha1_sign("hello", "key")
        r2 = hmac_sha1_sign("hello", "key")
        assert r1 == r2


class TestSDKSign:
    def test_format(self):
        result = compute_sdk_sign("123", "abc", "dev", "u2key")
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 十六进制 = 32 个字符
