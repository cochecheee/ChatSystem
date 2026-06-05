"""Repository layer — pure data access.

Repositories nhận `AsyncSession` qua __init__ và expose query methods.
Routers/services KHÔNG nên gọi `session.execute()` trực tiếp; gọi qua repo.

Quy tắc:
- Repo chỉ làm SQL/ORM. Không gọi service khác, không có business logic.
- Trả về SQLAlchemy entities hoặc primitives. Pydantic conversion ở layer trên.
- Mọi method là async.
"""

from .artifact_repo import ArtifactRepository
from .config_repo import ConfigRepository
from .finding_repo import FindingRepository
from .project_member_repo import ROLE_LATTICE, ProjectMemberRepository, role_satisfies
from .project_repo import ProjectRepository
from .suppression_repo import SuppressionRuleRepository, rule_matches
from .user_repo import UserRepository, seed_default_users

__all__ = [
    "ROLE_LATTICE",
    "ArtifactRepository",
    "ConfigRepository",
    "FindingRepository",
    "ProjectMemberRepository",
    "ProjectRepository",
    "SuppressionRuleRepository",
    "UserRepository",
    "role_satisfies",
    "rule_matches",
    "seed_default_users",
]
