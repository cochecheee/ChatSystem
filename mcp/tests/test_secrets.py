"""Fernet at-rest encryption tests — V2.8 A1."""
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from src.core import secrets as secrets_mod


@pytest.fixture(autouse=True)
def clear_fernet_cache():
    """Reset cache giữa các test (settings.FERNET_KEY thay đổi per test)."""
    secrets_mod._get_fernet.cache_clear()
    yield
    secrets_mod._get_fernet.cache_clear()


def _patch_key(key: str):
    return patch.object(secrets_mod.settings, "FERNET_KEY", key)


def test_no_key_passthrough():
    """FERNET_KEY rỗng → encrypt/decrypt no-op."""
    with _patch_key(""):
        assert secrets_mod.encrypt_field("secret") == "secret"
        assert secrets_mod.decrypt_field("secret") == "secret"
        assert secrets_mod.is_encryption_enabled() is False


def test_roundtrip_with_key():
    key = Fernet.generate_key().decode()
    with _patch_key(key):
        cipher = secrets_mod.encrypt_field("ghp_my_secret_token")
        assert cipher.startswith("gAAAA")
        assert cipher != "ghp_my_secret_token"
        plain = secrets_mod.decrypt_field(cipher)
        assert plain == "ghp_my_secret_token"
        assert secrets_mod.is_encryption_enabled() is True


def test_decrypt_tolerates_legacy_plaintext():
    """Row cũ chưa encrypt (V2.1-V2.7) → decrypt return as-is."""
    key = Fernet.generate_key().decode()
    with _patch_key(key):
        # Plaintext không có Fernet prefix → bypass decrypt
        assert secrets_mod.decrypt_field("plain-old-token") == "plain-old-token"
        assert secrets_mod.decrypt_field("AIzaSyOldKey") == "AIzaSyOldKey"


def test_encrypt_empty_passthrough():
    key = Fernet.generate_key().decode()
    with _patch_key(key):
        assert secrets_mod.encrypt_field("") == ""
        assert secrets_mod.decrypt_field("") == ""


def test_decrypt_wrong_key_returns_ciphertext():
    """Key đổi giữa encrypt và decrypt → decrypt fail gracefully (log + return cipher).

    Quan trọng: tránh crash service khi key rotate sai. Operator sẽ thấy
    'cipher' giá trị, biết phải re-set credentials.
    """
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    with _patch_key(key1):
        cipher = secrets_mod.encrypt_field("orig-token")
    secrets_mod._get_fernet.cache_clear()
    with _patch_key(key2):
        result = secrets_mod.decrypt_field(cipher)
        # Cipher trả về thay vì raise (graceful degrade)
        assert result == cipher
