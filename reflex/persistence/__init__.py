"""Persistence package for DataHub Reflex.

Provides SQLite-backed storage for all Reflex entities.
Import init_db() and call it at application startup.
"""

from reflex.persistence.database import init_db

__all__ = ["init_db"]
