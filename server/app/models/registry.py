"""Every mapped table, in one place: importing this populates `Base.metadata`.

`init_db` builds the schema from the models — the POC ships no Alembic revision —
so each table has to be imported before `create_all` runs, including the
append-only triggers `app.audit.models` registers on creation (UCM-11).

It lives next to `base` rather than in `app.models.__init__` on purpose: the
feature models import `app.models.base`, so a registry in the package's
`__init__` would import them while they are importing it.
"""

from app.audit.models import AuditEvent
from app.models.base import Base
from app.users.models import User

__all__ = ["AuditEvent", "Base", "User"]
