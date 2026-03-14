#!/usr/bin/env python3
"""清理重复边并添加唯一约束

运行步骤：
1. 找到所有重复的活跃边 (same source, target, predicate, group_id, expired_at IS NULL)
2. 对于每组重复边，只保留最早创建的那条，删除其他的
3. 添加唯一约束防止未来重复
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import Settings

# Load settings from .env
settings = Settings()

# Build sync database URL (replace asyncpg with psycopg2)
DATABASE_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

# Create sync engine
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def find_duplicate_edges(session):
    """查找所有重复的活跃边"""
    query = text("""
        SELECT
            group_id,
            source_entity_id,
            target_entity_id,
            predicate,
            COUNT(*) as count,
            ARRAY_AGG(id ORDER BY created_at) as edge_ids
        FROM entity_edges
        WHERE expired_at IS NULL
        GROUP BY group_id, source_entity_id, target_entity_id, predicate
        HAVING COUNT(*) > 1
    """)

    result = session.execute(query)
    return result.fetchall()


def merge_duplicate_edges(session):
    """合并重复边：保留最早的，删除其他的"""
    duplicates = find_duplicate_edges(session)

    if not duplicates:
        print("✅ 没有发现重复边")
        return 0

    print(f"🔍 发现 {len(duplicates)} 组重复边")

    total_removed = 0
    for dup in duplicates:
        group_id, source_id, target_id, predicate, count, edge_ids = dup

        # 保留第一条（最早的），删除其他的
        keep_id = edge_ids[0]
        remove_ids = edge_ids[1:]

        print(f"  - 边 ({source_id} → {target_id}, {predicate}): 保留 {keep_id}, 删除 {len(remove_ids)} 条")

        # 先收集要删除边的 episode_ids
        episode_query = text("""
            SELECT episode_ids FROM entity_edges WHERE id = :keep_id
        """)
        keep_episodes = session.execute(episode_query, {"keep_id": keep_id}).scalar() or []

        for remove_id in remove_ids:
            # 合并 episode_ids
            ep_query = text("""
                SELECT episode_ids FROM entity_edges WHERE id = :remove_id
            """)
            remove_episodes = session.execute(ep_query, {"remove_id": remove_id}).scalar() or []

            # 合并到保留的边
            all_episodes = list(set(keep_episodes + remove_episodes))
            update_query = text("""
                UPDATE entity_edges
                SET episode_ids = :episodes
                WHERE id = :keep_id
            """)
            session.execute(update_query, {"keep_id": keep_id, "episodes": all_episodes})
            keep_episodes = all_episodes

            # 删除重复边
            delete_query = text("DELETE FROM entity_edges WHERE id = :remove_id")
            session.execute(delete_query, {"remove_id": remove_id})
            total_removed += 1

    session.commit()
    print(f"✅ 已删除 {total_removed} 条重复边")
    return total_removed


def add_unique_constraint(session):
    """添加唯一约束（如果不存在）"""
    # 检查约束是否已存在
    check_query = text("""
        SELECT indexname FROM pg_indexes
        WHERE indexname = 'uq_active_edges'
    """)
    result = session.execute(check_query).fetchone()

    if result:
        print("✅ 唯一约束已存在")
        return

    print("🔧 添加唯一约束...")
    constraint_query = text("""
        CREATE UNIQUE INDEX uq_active_edges
        ON entity_edges (group_id, source_entity_id, target_entity_id, predicate)
        WHERE expired_at IS NULL
    """)
    session.execute(constraint_query)
    session.commit()
    print("✅ 唯一约束已添加")


def main():
    print("🚀 开始清理重复边...")

    session = SessionLocal()
    try:
        # 1. 合并重复边
        removed = merge_duplicate_edges(session)

        # 2. 添加唯一约束
        add_unique_constraint(session)

        print(f"\n✅ 完成！删除了 {removed} 条重复边")
    finally:
        session.close()


if __name__ == "__main__":
    main()
