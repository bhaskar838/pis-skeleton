"""Alembic environment for tenant databases. Online mode only; the URL comes from ``config.attributes``."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
url = config.attributes.get("sqlalchemy_url") or config.get_main_option("sqlalchemy.url")
if not url:
    raise RuntimeError("tenant migrations need a database URL (config.attributes['sqlalchemy_url'])")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
