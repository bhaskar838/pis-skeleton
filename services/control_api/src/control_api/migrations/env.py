"""Alembic environment for the Control DB (online only). URL comes from ``config.attributes``."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
url = config.attributes.get("sqlalchemy_url") or config.get_main_option("sqlalchemy.url")
if not url:
    raise RuntimeError("control migrations need a database URL")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
