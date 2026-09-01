from alembic import context
from sqlalchemy import engine_from_config, pool

import keel.db.models  # noqa: F401  (imported so autogenerate sees every table)
from keel.db.base import Base
from keel.settings import get_settings

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return get_settings().resolved_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
