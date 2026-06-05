"""V3.8 — password hashing for user login.

We call the `bcrypt` library directly instead of going through passlib's
CryptContext. passlib 1.7.4 (the pinned version) reads `bcrypt.__about__`
which bcrypt >= 4.1 removed, so `CryptContext(schemes=["bcrypt"])` raises
on hash() in this environment. bcrypt's own API (`hashpw`/`checkpw`) is
stable and dependency-free, so we use it.

bcrypt silently truncates the password at 72 bytes. We slice to 72 bytes
explicitly so hash and verify agree on the same input, and so a >72-byte
password doesn't behave surprisingly.
"""
from __future__ import annotations

import bcrypt

# Cost factor. 12 ≈ ~250ms/hash on commodity hardware — the standard
# interactive-login default. Higher = slower brute force but slower login.
_ROUNDS = 12
_MAX_BYTES = 72  # bcrypt hard limit; bytes beyond this are ignored.


def _clamp(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash string suitable for storing in users.password_hash."""
    return bcrypt.hashpw(_clamp(password), bcrypt.gensalt(rounds=_ROUNDS)).decode("ascii")


# A real bcrypt hash of a throwaway value, computed once at import. Login
# verifies an unknown username against this so a missing user costs the same
# bcrypt work as a wrong password — closing a timing side channel that would
# otherwise reveal which usernames exist.
_DUMMY_HASH = hash_password("invalid-account-placeholder")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of `password` against a stored bcrypt hash.

    Returns False (never raises) on malformed/empty hashes so a corrupt row
    can't 500 the login endpoint — it just fails authentication.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_clamp(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
