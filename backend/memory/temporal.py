"""Temporal upsert: conflict detection and fact lifecycle management.

Core algorithm:
  1. For each new triplet, find existing active edges with the same subject + predicate
  2. Semantic similarity narrows candidates
  3. LLM judges whether the new fact contradicts an existing fact
  4. If conflict → old fact gets expired_at = now
  5. Insert new fact with valid_at = episode time, expired_at = NULL
"""

import json
import logging
import re
import uuid
from datetime import datetime

from openai import OpenAI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from memory.embedder import get_embeddings
from memory.extractor import Triplet
from memory.models import EntityEdge
from memory.service import get_or_create_entity

logger = logging.getLogger(__name__)

CONFLICT_SYSTEM_PROMPT = """\
You are a fact conflict detector. Determine if two facts about the same subject are contradictory \
(i.e. the new fact invalidates / replaces the old fact).

Rules:
1. "Contradictory" means the two facts CANNOT both be true at the same time.
   - "Alice lives in Beijing" vs "Alice lives in Shanghai" → contradictory
   - "Alice works at Google" vs "Alice is a software engineer" → NOT contradictory (complementary)
   - "Alice is 25 years old" vs "Alice is 26 years old" → contradictory
2. If the new fact is simply more specific or adds detail, it is NOT contradictory.
3. Return ONLY a JSON object with "contradictory" (true/false) and "reason" (brief explanation).
"""


def check_contradiction(existing_fact: str, new_fact: str) -> bool:
    """Use LLM to determine if two facts are contradictory."""
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    user_msg = f"EXISTING fact: {existing_fact}\nNEW fact: {new_fact}"

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": CONFLICT_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = raw.strip()

        data = json.loads(raw)

        # Normalize keys: some LLMs return keys with extra quotes
        if isinstance(data, dict):
            data = {k.strip().strip('"'): v for k, v in data.items()}

        is_contradictory = data.get("contradictory", False)
        reason = data.get("reason", "")
        logger.info(
            "Conflict check: existing=%r vs new=%r -> contradictory=%s (%s)",
            existing_fact[:80], new_fact[:80], is_contradictory, reason,
        )
        return bool(is_contradictory)
    except Exception:
        logger.exception("Conflict check failed, assuming no contradiction")
        return False


def find_candidate_edges(
    session: Session,
    group_id: str,
    source_entity_id: uuid.UUID,
    predicate: str,
    new_fact_embedding: list[float] | None,
    similarity_threshold: float = 0.5,
    limit: int = 5,
) -> list[EntityEdge]:
    """Find active edges with the same source + predicate, ranked by semantic similarity."""

    if new_fact_embedding is not None:
        # Semantic search among active edges with same source + predicate
        stmt = text("""
            SELECT id, group_id, source_entity_id, target_entity_id,
                   predicate, fact, fact_embedding, valid_at, expired_at,
                   episode_ids, created_at,
                   1 - (fact_embedding <=> CAST(:vec AS vector)) AS score
            FROM entity_edges
            WHERE group_id = :gid
              AND source_entity_id = :sid
              AND predicate = :pred
              AND expired_at IS NULL
              AND fact_embedding IS NOT NULL
            ORDER BY fact_embedding <=> CAST(:vec AS vector)
            LIMIT :lim
        """)
        result = session.execute(stmt, {
            "vec": str(new_fact_embedding),
            "gid": group_id,
            "sid": str(source_entity_id),
            "pred": predicate,
            "lim": limit,
        })
        rows = result.fetchall()
        candidates = []
        for row in rows:
            if float(row.score) < similarity_threshold:
                continue
            edge = session.get(EntityEdge, row.id)
            if edge:
                candidates.append(edge)
        return candidates

    # Fallback: no embedding, just match by source + predicate
    stmt = (
        select(EntityEdge)
        .where(
            EntityEdge.group_id == group_id,
            EntityEdge.source_entity_id == source_entity_id,
            EntityEdge.predicate == predicate,
            EntityEdge.expired_at.is_(None),
        )
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def temporal_upsert(
    session: Session,
    group_id: str,
    triplet: Triplet,
    fact_embedding: list[float] | None,
    episode_id: uuid.UUID,
    valid_at: datetime,
) -> EntityEdge:
    """Insert a new fact edge with temporal conflict detection.

    1. Resolve entities
    2. Find candidate conflicting edges (same source + predicate, active)
    3. LLM checks contradiction for each candidate
    4. Expire contradicted edges
    5. Insert new edge
    """
    # 1. Resolve entities
    source = get_or_create_entity(session, group_id, triplet.subject, triplet.subject_type)
    target = get_or_create_entity(session, group_id, triplet.object, triplet.object_type)

    # 2. Find candidates
    candidates = find_candidate_edges(
        session, group_id, source.id, triplet.predicate, fact_embedding
    )

    # 3. Check contradiction and expire conflicting edges
    for candidate in candidates:
        # Skip if it's essentially the same fact
        if candidate.fact.strip().lower() == triplet.fact.strip().lower():
            # Same fact, just append episode_id for provenance
            if episode_id not in (candidate.episode_ids or []):
                candidate.episode_ids = (candidate.episode_ids or []) + [episode_id]
            logger.info("Duplicate fact, updated provenance: %s", candidate.fact[:80])
            session.flush()
            return candidate

        if check_contradiction(candidate.fact, triplet.fact):
            candidate.expired_at = valid_at
            logger.info(
                "Expired edge %s: %r (replaced by %r)",
                candidate.id, candidate.fact[:80], triplet.fact[:80],
            )

    # 4. Insert new edge
    new_edge = EntityEdge(
        group_id=group_id,
        source_entity_id=source.id,
        target_entity_id=target.id,
        predicate=triplet.predicate,
        fact=triplet.fact,
        fact_embedding=fact_embedding,
        valid_at=valid_at,
        expired_at=None,
        episode_ids=[episode_id],
    )
    session.add(new_edge)
    session.flush()

    logger.info("Inserted new edge %s: %s", new_edge.id, triplet.fact[:80])
    return new_edge
