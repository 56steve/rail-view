from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models. Imported by
    `app/models/__init__.py` (so every model registers on this metadata)
    and by `alembic/env.py` (so autogenerate can see the full schema).
    """
