"""One-off migration script: add MVP columns to existing tables."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

STMTS = [
    # sim_tasks 新增字段
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS goal VARCHAR",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS scene_type VARCHAR",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS scene_config JSONB",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS sim_start_time TIMESTAMPTZ",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS sim_end_time TIMESTAMPTZ",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS time_step_unit VARCHAR DEFAULT 'day'",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS num_timelines INTEGER DEFAULT 3",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS blackswan_enabled BOOLEAN DEFAULT FALSE",
    "ALTER TABLE sim_tasks ADD COLUMN IF NOT EXISTS blackswan_prob FLOAT DEFAULT 0.0",
    # entities 新增字段
    "ALTER TABLE entities ADD COLUMN IF NOT EXISTS display_name VARCHAR",
    "ALTER TABLE entities ADD COLUMN IF NOT EXISTS metadata_ JSONB",
    # entity_edges 新增字段
    "ALTER TABLE entity_edges ADD COLUMN IF NOT EXISTS generated_by VARCHAR",
    "ALTER TABLE entity_edges ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 1.0",
]

async def migrate():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        for s in STMTS:
            await conn.execute(text(s))
            print("OK:", s[:70])
    await engine.dispose()
    print("\nMigration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
