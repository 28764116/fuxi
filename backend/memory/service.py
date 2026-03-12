import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from memory.embedder import get_embeddings
from memory.models import Entity, EntityEdge, Episode
from memory.schemas import EpisodeCreate


async def ingest_episode(session: AsyncSession, data: EpisodeCreate) -> Episode:
    episode = Episode(
        group_id=data.group_id,
        thread_id=data.thread_id,
        role=data.role,
        content=data.content,
        source_type=data.source_type,
        valid_at=data.valid_at,
    )
    session.add(episode)
    await session.commit()
    await session.refresh(episode)

    # Push to Celery for async processing
    from worker import celery_app

    celery_app.send_task("memory.process_episode", args=[str(episode.id)])

    return episode


# --- Entity dedup (sync, for Celery tasks) ---


def get_or_create_entity(
    session: Session, group_id: str, name: str, entity_type: str
) -> Entity:
    """Find an existing entity by normalized name within a group, or create a new one."""
    normalized_name = name.strip().lower()
    stmt = select(Entity).where(
        Entity.group_id == group_id,
        Entity.name == normalized_name,
    )
    entity = session.execute(stmt).scalars().first()
    if entity:
        return entity

    entity = Entity(
        group_id=group_id,
        name=normalized_name,
        entity_type=entity_type,
    )
    session.add(entity)
    session.flush()
    return entity


# --- Semantic search (async, for API) ---


async def search_edges(
    session: AsyncSession,
    query: str,
    group_id: str,
    limit: int = 5,
    include_expired: bool = False,
) -> list[tuple[EntityEdge, float]]:
    """Search entity edges by semantic similarity on fact_embedding.

    By default only returns active (non-expired) facts.
    """
    embeddings = get_embeddings([query], embedding_type="query")
    if not embeddings:
        return []

    query_vec = embeddings[0]

    expired_filter = "" if include_expired else "AND expired_at IS NULL"

    stmt = text(f"""
        SELECT id, group_id, source_entity_id, target_entity_id,
               predicate, fact, valid_at, expired_at, episode_ids, created_at,
               1 - (fact_embedding <=> CAST(:vec AS vector)) AS score
        FROM entity_edges
        WHERE group_id = :gid AND fact_embedding IS NOT NULL
        {expired_filter}
        ORDER BY fact_embedding <=> CAST(:vec AS vector)
        LIMIT :lim
    """)
    result = await session.execute(
        stmt, {"vec": str(query_vec), "gid": group_id, "lim": limit}
    )
    rows = result.fetchall()

    edges_with_scores = []
    for row in rows:
        edge = EntityEdge(
            id=row.id,
            group_id=row.group_id,
            source_entity_id=row.source_entity_id,
            target_entity_id=row.target_entity_id,
            predicate=row.predicate,
            fact=row.fact,
            valid_at=row.valid_at,
            expired_at=row.expired_at,
            episode_ids=row.episode_ids,
            created_at=row.created_at,
        )
        edges_with_scores.append((edge, float(row.score)))

    return edges_with_scores


async def search_entities(
    session: AsyncSession, query: str, group_id: str, limit: int = 5
) -> list[tuple[Entity, float]]:
    """Search entities by semantic similarity on summary_embedding."""
    embeddings = get_embeddings([query], embedding_type="query")
    if not embeddings:
        return []

    query_vec = embeddings[0]

    stmt = text("""
        SELECT id, group_id, name, entity_type, summary, created_at, updated_at,
               1 - (summary_embedding <=> CAST(:vec AS vector)) AS score
        FROM entities
        WHERE group_id = :gid AND summary_embedding IS NOT NULL
        ORDER BY summary_embedding <=> CAST(:vec AS vector)
        LIMIT :lim
    """)
    result = await session.execute(
        stmt, {"vec": str(query_vec), "gid": group_id, "lim": limit}
    )
    rows = result.fetchall()

    entities_with_scores = []
    for row in rows:
        entity = Entity(
            id=row.id,
            group_id=row.group_id,
            name=row.name,
            entity_type=row.entity_type,
            summary=row.summary,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        entities_with_scores.append((entity, float(row.score)))

    return entities_with_scores


# --- Temporal queries ---


async def get_entity_facts(
    session: AsyncSession,
    entity_id: uuid.UUID,
    active_only: bool = True,
) -> list[EntityEdge]:
    """Get all facts (edges) related to an entity."""
    conditions = [
        (EntityEdge.source_entity_id == entity_id)
        | (EntityEdge.target_entity_id == entity_id),
    ]
    if active_only:
        conditions.append(EntityEdge.expired_at.is_(None))

    stmt = (
        select(EntityEdge)
        .where(*conditions)
        .order_by(EntityEdge.valid_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_entity_facts_at(
    session: AsyncSession,
    entity_id: uuid.UUID,
    point_in_time: datetime,
) -> list[EntityEdge]:
    """Time-travel query: get facts that were valid at a specific point in time.

    A fact is valid at time T if:
      valid_at <= T AND (expired_at IS NULL OR expired_at > T)
    """
    stmt = (
        select(EntityEdge)
        .where(
            (EntityEdge.source_entity_id == entity_id)
            | (EntityEdge.target_entity_id == entity_id),
            EntityEdge.valid_at <= point_in_time,
            (EntityEdge.expired_at.is_(None)) | (EntityEdge.expired_at > point_in_time),
        )
        .order_by(EntityEdge.valid_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- Context assembly ---


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 chars per token for Chinese, ~4 chars for English."""
    return max(len(text) // 2, 1)


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget."""
    estimated = _estimate_tokens(text)
    if estimated <= max_tokens:
        return text
    # Approximate char limit
    char_limit = max_tokens * 2
    return text[:char_limit] + "\n...(已截断)"


async def get_context(
    session: AsyncSession, thread_id: uuid.UUID, limit: int = 20
) -> tuple[list[Episode], str]:
    """Assemble LLM context with three layers:

    1. User/entity profile summaries (compressed long-term memory)
    2. Relevant active facts via semantic search (mid-term memory)
    3. Recent N conversation messages (short-term memory)

    Each layer gets a token budget slice.
    """
    from app.config import settings

    total_budget = settings.context_max_tokens
    # Budget allocation: 15% profile, 25% facts, 60% conversation
    profile_budget = int(total_budget * 0.15)
    facts_budget = int(total_budget * 0.25)
    convo_budget = int(total_budget * 0.60)

    # Fetch recent episodes
    stmt = (
        select(Episode)
        .where(Episode.thread_id == thread_id)
        .order_by(Episode.valid_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    episodes = list(result.scalars().all())
    episodes.reverse()

    sections = []

    if episodes:
        group_id = episodes[0].group_id
        last_user_msgs = [ep for ep in episodes if ep.role == "user"]
        query_text = last_user_msgs[-1].content if last_user_msgs else episodes[-1].content

        # --- Layer 1: Entity profile summaries ---
        entities_with_scores = await search_entities(session, query_text, group_id, limit=3)
        if entities_with_scores:
            profile_lines = []
            for entity, _score in entities_with_scores:
                if entity.summary:
                    profile_lines.append(f"- {entity.summary}")
            if profile_lines:
                profile_text = "\n".join(profile_lines)
                profile_text = _truncate_to_budget(profile_text, profile_budget)
                sections.append(f"[用户画像]\n{profile_text}")

        # --- Layer 2: Relevant facts via semantic search ---
        edges_with_scores = await search_edges(
            session, query_text, group_id, limit=5, include_expired=False
        )
        if edges_with_scores:
            fact_lines = [f"- {edge.fact}" for edge, _score in edges_with_scores]
            facts_text = "\n".join(fact_lines)
            facts_text = _truncate_to_budget(facts_text, facts_budget)
            sections.append(f"[相关事实]\n{facts_text}")

    # --- Layer 3: Recent conversation ---
    convo_lines = []
    for ep in reversed(episodes):
        line = f"[{ep.role}] {ep.content}"
        convo_lines.insert(0, line)
        if _estimate_tokens("\n".join(convo_lines)) > convo_budget:
            convo_lines.pop(0)
            break

    if convo_lines:
        sections.append(f"[最近对话]\n" + "\n".join(convo_lines))

    context = "\n\n".join(sections) if sections else ""
    return episodes, context
