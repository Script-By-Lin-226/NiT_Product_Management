from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config.configuration import settings
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import inspect, text

def _ensure_async_database_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url

engine = create_async_engine(_ensure_async_database_url(settings.DATABASE_URL))
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

async def database_initialize():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_runtime_schema_updates)


def _apply_runtime_schema_updates(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if not inspector.has_table("inventory_logs"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("inventory_logs")}
    missing_columns = []
    if "actor_name" not in existing_columns:
        missing_columns.append("ALTER TABLE inventory_logs ADD COLUMN actor_name VARCHAR(255)")
    if "actor_class" not in existing_columns:
        missing_columns.append("ALTER TABLE inventory_logs ADD COLUMN actor_class VARCHAR(255)")
    if "uniform_category" not in existing_columns:
        missing_columns.append("ALTER TABLE inventory_logs ADD COLUMN uniform_category VARCHAR(255)")
    if "given_to" not in existing_columns:
        missing_columns.append("ALTER TABLE inventory_logs ADD COLUMN given_to VARCHAR(255)")
    if "department" not in existing_columns:
        missing_columns.append("ALTER TABLE inventory_logs ADD COLUMN department VARCHAR(255)")

    for statement in missing_columns:
        sync_conn.execute(text(statement))
