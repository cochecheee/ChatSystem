"""Project repository.

V2.8 A1 — github_token + gemini_api_key được Fernet encrypt khi ghi và
auto-decrypt khi đọc (transparent với caller). FERNET_KEY chưa set →
plaintext (legacy compat). Xem core/secrets.py.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.secrets import decrypt_field, encrypt_field
from ..models.entities import Project

_ENCRYPTED_FIELDS = ("github_token", "gemini_api_key")


def _decrypt_project(p: Project | None) -> Project | None:
    """In-place decrypt sensitive fields. Idempotent qua heuristic prefix."""
    if p is None:
        return None
    for fld in _ENCRYPTED_FIELDS:
        v = getattr(p, fld, "")
        if v:
            setattr(p, fld, decrypt_field(v))
    return p


def _encrypt_kwargs(kwargs: dict) -> dict:
    """Encrypt sensitive fields trong dict pre-insert/update."""
    out = dict(kwargs)
    for fld in _ENCRYPTED_FIELDS:
        if fld in out and out[fld]:
            out[fld] = encrypt_field(out[fld])
    return out


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, project_id: int) -> Project | None:
        return _decrypt_project(await self.session.get(Project, project_id))

    async def get_by_github_url(self, github_url: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.github_url == github_url)
        )
        return _decrypt_project(result.scalar_one_or_none())

    async def list_all(self) -> list[Project]:
        result = await self.session.execute(select(Project))
        rows = list(result.scalars().all())
        for p in rows:
            _decrypt_project(p)
        return rows

    async def create(self, **fields) -> Project:
        """Create project; encrypt sensitive fields trước khi insert.

        `name` + `github_url` required; các field credentials encrypt
        khi FERNET_KEY set, else lưu plaintext (legacy compat).
        """
        project = Project(**_encrypt_kwargs(fields))
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        # Decrypt cho caller (ProjectOut + UI sẽ thấy plaintext sau commit)
        return _decrypt_project(project)

    async def get_or_create_by_github_url(
        self, *, name: str, github_url: str, **extra,
    ) -> Project:
        existing = await self.get_by_github_url(github_url)
        if existing is not None:
            return existing
        return await self.create(name=name, github_url=github_url, **extra)

    async def update(self, project: Project, fields: dict) -> Project:
        """Apply non-None fields, encrypt sensitive ones, commit, return refreshed."""
        encrypted = _encrypt_kwargs(fields)
        for k, v in encrypted.items():
            if v is not None and hasattr(project, k):
                setattr(project, k, v)
        await self.session.commit()
        await self.session.refresh(project)
        return _decrypt_project(project)

    async def list_active(self) -> list[Project]:
        """Active projects with credentials wired — what the poller iterates."""
        result = await self.session.execute(
            select(Project).where(
                Project.active == 1,
                Project.github_token != "",
                Project.github_owner != "",
                Project.github_repo != "",
            )
        )
        rows = list(result.scalars().all())
        for p in rows:
            _decrypt_project(p)
        return rows

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.commit()
