from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from keel.paths import migrations_dir


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    config.set_main_option("sqlalchemy.url", url)
    return config


def head_revision(config: Config) -> str | None:
    return ScriptDirectory.from_config(config).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def schema_is_current(engine: Engine, config: Config) -> bool:
    return current_revision(engine) == head_revision(config)


def upgrade_to_head(config: Config) -> None:
    command.upgrade(config, "head")


def create_revision(config: Config, message: str) -> None:
    command.revision(config, message=message, autogenerate=True)
