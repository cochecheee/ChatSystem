"""Repository layer — pure data access.

Repositories nhận `AsyncSession` qua __init__ và expose query methods.
Routers/services KHÔNG nên gọi `session.execute()` trực tiếp; gọi qua repo.

Quy tắc:
- Repo chỉ làm SQL/ORM. Không gọi service khác, không có business logic.
- Trả về SQLAlchemy entities hoặc primitives. Pydantic conversion ở layer trên.
- Mọi method là async.
"""

from .finding_repo import FindingRepository
from .project_repo import ProjectRepository
from .artifact_repo import ArtifactRepository
from .config_repo import ConfigRepository

__all__ = [
    "FindingRepository",
    "ProjectRepository",
    "ArtifactRepository",
    "ConfigRepository",
]
