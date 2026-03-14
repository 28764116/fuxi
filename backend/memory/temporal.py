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
) -> list[tuple["EntityEdge", float]]:
    """Find active edges with the same source + predicate.

    Returns list of (edge, similarity_score) tuples.
    Only edges with similarity >= similarity_threshold are returned.
    """

    if new_fact_embedding is not None:
        stmt = text("""
            SELECT id,
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
            score = float(row.score)
            if score < similarity_threshold:
                continue
            edge = session.get(EntityEdge, row.id)
            if edge:
                candidates.append((edge, score))
        return candidates

    # Fallback: no embedding, return with score=0.0
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
    return [(e, 0.0) for e in session.execute(stmt).scalars().all()]


def temporal_upsert(
    session: Session,
    group_id: str,
    triplet: Triplet,
    fact_embedding: list[float] | None,
    episode_id: uuid.UUID,
    valid_at: datetime,
    generated_by: str = "extraction",
    confidence: float | None = None,
) -> EntityEdge:
    """Insert a new fact edge with temporal conflict detection.

    1. Resolve entities
    2. Find candidate conflicting edges (same source + predicate, active)
    3. LLM checks contradiction for each candidate
    4. Expire contradicted edges
    5. Insert new edge
    """
    # 1. Resolve entities (with summaries from extraction)
    source = get_or_create_entity(
        session, group_id, triplet.subject, triplet.subject_type,
        summary=getattr(triplet, "subject_summary", "")
    )
    target = get_or_create_entity(
        session, group_id, triplet.object, triplet.object_type,
        summary=getattr(triplet, "object_summary", "")
    )

    # 2. First, check if this EXACT triplet already exists (防止重复插入)
    exact_match_stmt = select(EntityEdge).where(
        EntityEdge.group_id == group_id,
        EntityEdge.source_entity_id == source.id,
        EntityEdge.target_entity_id == target.id,
        EntityEdge.predicate == triplet.predicate,
        EntityEdge.expired_at.is_(None),
    )
    exact_match = session.execute(exact_match_stmt).scalars().first()

    if exact_match:
        # 完全相同的三元组已存在，只更新 provenance
        if episode_id not in (exact_match.episode_ids or []):
            exact_match.episode_ids = (exact_match.episode_ids or []) + [episode_id]
        # 如果新 fact 更详细，更新 fact
        if len(triplet.fact) > len(exact_match.fact):
            exact_match.fact = triplet.fact
            if fact_embedding:
                exact_match.fact_embedding = fact_embedding
        logger.info("Exact triplet exists, updated: %s → [%s] → %s",
                   source.display_name or source.name, triplet.predicate,
                   target.display_name or target.name)
        session.flush()
        return exact_match

    # 3. Find candidates (same source + target + predicate) for similarity check
    candidates = find_candidate_edges(
        session, group_id, source.id, triplet.predicate, fact_embedding
    )

    # Filter candidates: prioritize those with the same target entity
    same_target_candidates = [(c, s) for c, s in candidates if c.target_entity_id == target.id]
    other_candidates = [(c, s) for c, s in candidates if c.target_entity_id != target.id]

    # 3. Check contradiction and expire conflicting edges
    # First, check same-target candidates (exact duplicates or updates)
    for candidate, score in same_target_candidates:
        # CRITICAL: If source + target + predicate are identical, treat as duplicate
        # regardless of fact text differences (they describe the same relationship)
        # We simply update the fact to the latest version and merge provenance

        # Check if fact is similar enough to merge (instead of expire + insert)
        # Threshold: 0.90 for embedding similarity, or exact text match
        is_similar_fact = (
            score >= 0.90 or
            candidate.fact.strip().lower() == triplet.fact.strip().lower() or
            # Even if score is low (e.g., no embedding), same triplet = merge
            (score == 0.0 and candidate.fact.strip() == triplet.fact.strip())
        )

        if is_similar_fact:
            # Exact or similar: just update provenance, keep existing fact
            if episode_id not in (candidate.episode_ids or []):
                candidate.episode_ids = (candidate.episode_ids or []) + [episode_id]
            logger.info("Duplicate triplet (score=%.2f), merged provenance: %s → %s → %s",
                       score, source.display_name or source.name,
                       triplet.predicate, target.display_name or target.name)
            session.flush()
            return candidate

        # If fact is different enough, check if contradictory
        if check_contradiction(candidate.fact, triplet.fact):
            # Expire old fact and continue to insert new one
            candidate.expired_at = valid_at
            logger.info(
                "Expired edge %s (score=%.2f): %r (replaced by %r)",
                candidate.id, score, candidate.fact[:80], triplet.fact[:80],
            )
        else:
            # Same relation but facts don't contradict (e.g., both true)
            # Update to latest fact but keep both as valid
            if episode_id not in (candidate.episode_ids or []):
                candidate.episode_ids = (candidate.episode_ids or []) + [episode_id]
            # Update fact to latest version
            candidate.fact = triplet.fact
            if fact_embedding:
                candidate.fact_embedding = fact_embedding
            logger.info("Updated fact for same triplet: %s → %s → %s",
                       source.display_name or source.name,
                       triplet.predicate, target.display_name or target.name)
            session.flush()
            return candidate

    # Then, check other candidates (different targets - usually not duplicates)
    # We don't check these for duplicates, only for contradictions
    for candidate, score in other_candidates:
        # Only check contradiction if very similar
        if score >= 0.90 and check_contradiction(candidate.fact, triplet.fact):
            candidate.expired_at = valid_at
            logger.info(
                "Expired conflicting edge %s (different target, score=%.2f): %r",
                candidate.id, score, candidate.fact[:80],
            )

    # 4. Insert new edge (with unique constraint protection)
    from sqlalchemy.exc import IntegrityError

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
        generated_by=generated_by,
        confidence=confidence if confidence is not None else getattr(triplet, "confidence", None),
    )
    session.add(new_edge)

    try:
        session.flush()
        logger.info("Inserted new edge %s: %s", new_edge.id, triplet.fact[:80])
        return new_edge
    except IntegrityError as e:
        # Unique constraint violation: another transaction already inserted this edge
        # Roll back this edge, re-query, and merge provenance
        session.rollback()
        logger.warning("Unique constraint hit for (%s → %s, %s), merging with existing edge",
                      source.name, target.display_name or target.name, triplet.predicate)

        # Re-query the existing edge
        existing_stmt = select(EntityEdge).where(
            EntityEdge.group_id == group_id,
            EntityEdge.source_entity_id == source.id,
            EntityEdge.target_entity_id == target.id,
            EntityEdge.predicate == triplet.predicate,
            EntityEdge.expired_at.is_(None),
        )
        existing = session.execute(existing_stmt).scalars().first()

        if existing:
            # Merge provenance
            if episode_id not in (existing.episode_ids or []):
                existing.episode_ids = (existing.episode_ids or []) + [episode_id]
            # Update fact if new one is more detailed
            if len(triplet.fact) > len(existing.fact):
                existing.fact = triplet.fact
                if fact_embedding:
                    existing.fact_embedding = fact_embedding
            session.flush()
            logger.info("Merged with existing edge %s", existing.id)
            return existing
        else:
            # Edge was deleted between our check and flush, retry once
            logger.warning("Edge disappeared after constraint violation, retrying insert")
            session.add(new_edge)
            session.flush()
            return new_edge
