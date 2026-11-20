"""Alembic environment: reads DATABASE_URL and uses Base.metadata."""

from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db import Base, get_database_url, make_engine

config = context.config

if config.config_file_name is not None:
    # Keep the application's loggers (and any pytest log capture) intact.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = make_engine(get_database_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
