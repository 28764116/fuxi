from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Async engine (for FastAPI)
engine = create_async_engine(settings.database_url, echo=(settings.app_env == "development"))
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine (for Celery tasks)
sync_database_url = settings.database_url.replace("+asyncpg", "+psycopg2")
sync_engine = create_engine(sync_database_url, echo=(settings.app_env == "development"))
sync_session_factory = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
