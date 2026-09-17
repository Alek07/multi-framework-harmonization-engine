"""Every mapped table, in one place: importing this populates `Base.metadata`.

`init_db` builds the schema from the models — the POC ships no Alembic revision —
so each table has to be imported before `create_all` runs, including the
append-only triggers `app.audit.models` registers on creation.

It lives next to `base` rather than in `app.models.__init__` on purpose: the
feature models import `app.models.base`, so a registry in the package's
`__init__` would import them while they are importing it.
"""

from app.audit.models import AuditEvent
from app.models.base import Base

__all__ = ["AuditEvent", "Base"]
