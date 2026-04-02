"""Services package."""

from backend.config import settings as _settings

if _settings.db_backend == "mongodb":
    from backend.services.database import DatabaseService
else:
    from backend.services.database_sqlite import DatabaseService

__all__ = ["DatabaseService"]
