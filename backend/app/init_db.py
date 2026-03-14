"""Database initialization script.

Usage: python -m app.init_db
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

# Import models so they register with Base.metadata
import memory.models  # noqa: F401
import simulation.models  # noqa: F401
# sim_reports 依赖 sim_worldlines，需确保 simulation.models 已导入


async def init_db() -> None:
    engine = create_async_engine(settings.database_url)

    async with engine.begin() as conn:
        # Ensure pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        # HNSW vector indexes (cannot be declared in SQLAlchemy Index())
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_edges_embedding
            ON entity_edges USING hnsw (fact_embedding vector_cosine_ops)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_entities_embedding
            ON entities USING hnsw (summary_embedding vector_cosine_ops)
        """))
        # sim_agents: 按任务 + 影响力排序（推演主循环高频查询）
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sim_agents_task_influence
            ON sim_agents (task_id, influence_weight DESC)
        """))
        # sim_worldline_events: 按世界线 + 步骤顺序（时间轴渲染）
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sim_events_worldline_step
            ON sim_worldline_events (worldline_id, step_index ASC)
        """))
        # sim_checkpoints: 按世界线 + agent + 步骤（状态恢复）
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sim_checkpoints_lookup
            ON sim_checkpoints (worldline_id, agent_id, step_index DESC)
        """))

    await engine.dispose()
    print("Tables and indexes created successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())
