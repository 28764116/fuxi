import logging
import uuid

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="memory.process_episode")
def process_episode(episode_id: str) -> None:
    """Process a newly ingested episode.

    1. Read episode content from DB
    2. Extract entity-relation triplets via LLM
    3. Temporal upsert: conflict detection + fact lifecycle management
    4. Update entity summaries
    """
    from app.database import sync_session_factory
    from memory.embedder import get_embeddings
    from memory.extractor import extract_triplets
    from memory.models import Episode
    from memory.temporal import temporal_upsert

    logger.info("Processing episode %s", episode_id)

    with sync_session_factory() as session:
        # 1. Load episode
        episode = session.get(Episode, uuid.UUID(episode_id))
        if not episode:
            logger.error("Episode %s not found", episode_id)
            return

        # 2. Build context from recent episodes in the same thread
        from sqlalchemy import select

        ctx_stmt = (
            select(Episode)
            .where(
                Episode.thread_id == episode.thread_id,
                Episode.id != episode.id,
            )
            .order_by(Episode.valid_at.desc())
            .limit(5)
        )
        recent = list(session.execute(ctx_stmt).scalars().all())
        recent.reverse()
        context = "\n".join(f"[{ep.role}] {ep.content}" for ep in recent)

        # 3. Extract triplets with context
        triplets = extract_triplets(episode.content, context=context)
        if not triplets:
            logger.info("No triplets extracted from episode %s", episode_id)
            return

        # 3. Generate fact embeddings in batch
        facts = [t.fact for t in triplets]
        fact_embeddings = get_embeddings(facts)
        if len(fact_embeddings) != len(triplets):
            logger.warning(
                "Embedding count mismatch: %d triplets, %d embeddings",
                len(triplets),
                len(fact_embeddings),
            )
            while len(fact_embeddings) < len(triplets):
                fact_embeddings.append(None)

        # 4. Temporal upsert each triplet (each in its own savepoint)
        for triplet, embedding in zip(triplets, fact_embeddings):
            savepoint = session.begin_nested()
            try:
                temporal_upsert(
                    session=session,
                    group_id=episode.group_id,
                    triplet=triplet,
                    fact_embedding=embedding,
                    episode_id=episode.id,
                    valid_at=episode.valid_at,
                )
                savepoint.commit()
            except Exception:
                logger.exception("Failed to upsert triplet: %s", triplet.fact[:80])
                savepoint.rollback()

        session.commit()

        # 5. Update entity summaries and embeddings
        _update_entity_summaries(session, episode.group_id, triplets)

        logger.info(
            "Episode %s processed: %d triplets",
            episode_id,
            len(triplets),
        )


def _update_entity_summaries(session, group_id: str, triplets) -> None:
    """Collect active facts per entity and regenerate summary + embedding."""
    from sqlalchemy import select

    from memory.embedder import get_embeddings
    from memory.models import Entity, EntityEdge

    entity_names = set()
    for t in triplets:
        entity_names.add(t.subject.strip().lower())
        entity_names.add(t.object.strip().lower())

    for name in entity_names:
        stmt = select(Entity).where(
            Entity.group_id == group_id,
            Entity.name == name,
        )
        entity = session.execute(stmt).scalars().first()
        if not entity:
            continue

        # Only gather active (non-expired) facts
        edge_stmt = select(EntityEdge.fact).where(
            EntityEdge.group_id == group_id,
            EntityEdge.expired_at.is_(None),
            (EntityEdge.source_entity_id == entity.id)
            | (EntityEdge.target_entity_id == entity.id),
        ).limit(20)
        facts = session.execute(edge_stmt).scalars().all()

        if facts:
            summary = f"{entity.name} ({entity.entity_type}): " + "; ".join(facts)
            entity.summary = summary

    session.flush()

    entities_to_embed = []
    for name in entity_names:
        stmt = select(Entity).where(
            Entity.group_id == group_id,
            Entity.name == name,
        )
        entity = session.execute(stmt).scalars().first()
        if entity and entity.summary:
            entities_to_embed.append(entity)

    if entities_to_embed:
        summaries = [e.summary for e in entities_to_embed]
        embeddings = get_embeddings(summaries)
        if len(embeddings) == len(entities_to_embed):
            for entity, emb in zip(entities_to_embed, embeddings):
                entity.summary_embedding = emb

    session.commit()
