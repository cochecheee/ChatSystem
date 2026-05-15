"""Fernet at-rest encryption cho per-project credentials — V2.8 Phase A1.

Used by ProjectRepository khi đọc/ghi `github_token` + `gemini_api_key`.
Khi `FERNET_KEY` env không set → no-op (plaintext, single-tenant legacy).

Key generation:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Store key trong Render Environment (sync:false). Mất key = mất khả năng
decrypt → credentials phải reset thủ công cho từng project. Document
trong SECRETS.txt thời điểm generate + ai sở hữu.

Compatibility với plaintext rows cũ:
  Encrypt format = bytes Fernet token (starts with "gAAAA"). Plain value
  không có prefix này. `decrypt_field` tolerant — nếu input không match
  Fernet token, return raw (legacy plaintext row).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

log = logging.getLogger(__name__)

# Fernet tokens start with "gAAAA" + base64. Heuristic — nếu rỗng hoặc
# không bắt đầu prefix này, treat as legacy plaintext.
_FERNET_PREFIX = "gAAAA"


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    """Return Fernet instance nếu FERNET_KEY set; None để skip encryption."""
    if not settings.FERNET_KEY:
        return None
    try:
        return Fernet(settings.FERNET_KEY.encode())
    except Exception:  # noqa: BLE001
        log.exception("Invalid FERNET_KEY — encryption disabled")
        return None


def encrypt_field(plaintext: str) -> str:
    """Encrypt single credential string. Empty → empty (skip).

    FERNET_KEY chưa set → return plaintext (no-op).
    """
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_field(value: str) -> str:
    """Decrypt single credential string. Tolerant với legacy plaintext.

    Heuristic: value start với 'gAAAA' → try decrypt. Else assume
    plaintext (legacy V2.1-V2.7 rows trước khi key được set).

    FERNET_KEY chưa set → return value as-is (no-op).
    """
    if not value:
        return value
    if not value.startswith(_FERNET_PREFIX):
        return value
    fernet = _get_fernet()
    if fernet is None:
        log.warning("Encrypted value found but FERNET_KEY unset — returning ciphertext")
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        log.exception("Decrypt failed — wrong key or tampered value")
        return value


def is_encryption_enabled() -> bool:
    """Helper cho config endpoint / health check để biết key có wire không."""
    return _get_fernet() is not None
