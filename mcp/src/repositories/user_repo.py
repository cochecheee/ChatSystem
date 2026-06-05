"""V3.8 — user accounts for password login.

Identity used to be a bare JWT `sub` string. This repo backs the new
`users` table: it verifies bcrypt credentials at login and seeds the
existing population (cochecheee + every project_members username) with a
default password on first boot.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.security import _DUMMY_HASH, hash_password, verify_password
from ..models.entities import ProjectMember, UserAccount

log = logging.getLogger(__name__)

# Valid global roles (mirrors the /auth/token validator and JWT `role` claim).
VALID_ROLES = {"developer", "security_lead", "admin"}

# Usernames that always exist with an elevated global role, independent of
# project membership. cochecheee is the operator/owner account (seed convention).
ADMIN_USERNAMES = {"cochecheee"}


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, username: str) -> UserAccount | None:
        return await self.session.get(UserAccount, username)

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(UserAccount))
        return int(result.scalar_one())

    async def create(self, *, username: str, password: str, role: str = "developer") -> UserAccount:
        user = UserAccount(
            username=username,
            password_hash=hash_password(password),
            role=role if role in VALID_ROLES else "developer",
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def verify_credentials(self, username: str, password: str) -> UserAccount | None:
        """Return the user iff the password matches, else None.

        Always runs a bcrypt verify (against a dummy hash when the user is
        absent) so the response time doesn't leak whether a username exists.
        """
        user = await self.get(username)
        if user is None:
            # Constant-ish work to blunt username enumeration via timing.
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


async def seed_default_users(session: AsyncSession) -> int:
    """Ensure a user row exists for cochecheee + every project member.

    Idempotent and additive: only creates rows for usernames that have NO
    user yet. NEVER overwrites an existing password or role — so rotating a
    password and rebooting won't reset it. Returns the number of users created.

    Role assignment: ADMIN_USERNAMES → admin; everyone else → developer.
    (Per-project authority still comes from ProjectMember; this is just the
    global role / JWT claim baseline.)
    """
    repo = UserRepository(session)

    # Collect the target population: admin accounts + distinct member usernames.
    usernames: set[str] = set(ADMIN_USERNAMES)
    rows = await session.execute(select(ProjectMember.username).distinct())
    usernames.update(u for (u,) in rows.all() if u)

    created = 0
    default_pw = settings.DEFAULT_USER_PASSWORD
    for username in sorted(usernames):
        if await repo.get(username) is not None:
            continue
        role = "admin" if username in ADMIN_USERNAMES else "developer"
        await repo.create(username=username, password=default_pw, role=role)
        created += 1

    if created:
        log.info("Seeded %d user(s) with default password", created)
    return created
