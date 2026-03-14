"""Worldline bootstrap: initialize parallel timelines for multi-world simulation.

Steps:
  1. LLM generates N differentiated initial assumptions (optimistic/neutral/pessimistic)
  2. Create SimWorldline records with unique graph_namespaces
  3. clone_graph: deep-copy entity_edges from base_namespace → worldline_namespace
  4. Write each worldline's initial assumption as a new fact via temporal_upsert (generated_by='bootstrap')
"""

import json
import logging
import re
import uuid
from datetime import datetime

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from memory.extractor import Triplet
from memory.models import Entity, EntityEdge
from memory.temporal import temporal_upsert
from simulation.models import SimTask, SimWorldline
from simulation.scene_registry import get_scene

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ASSUMPTION_SYSTEM_PROMPT = """\
You are a scenario planning expert for multi-world simulation.
Given a background context and an analytical goal, generate {n} distinct initial assumptions \
that will seed {n} parallel worldlines (timelines) for simulation.

The assumptions should represent a spread of plausible starting conditions:
- 1 optimistic scenario (favorable initial conditions)
- 1 neutral/baseline scenario  
- 1 pessimistic scenario (unfavorable initial conditions)
- (If N > 3, add additional variants between these poles)

Each assumption is a concise paragraph (3-5 sentences) describing the initial state of the world \
at the start of the simulation, including key conditions and tensions.

Return a JSON array of objects:
[
  {{
    "assumption_type": "optimistic" | "neutral" | "pessimistic",
    "title": "<short title for this worldline>",
    "assumption": "<the full initial assumption paragraph>",
    "key_conditions": ["<condition 1>", "<condition 2>", ...]
  }},
  ...
]

Return ONLY the JSON array.
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def bootstrap_worldlines(
    session: Session,
    task: SimTask,
    base_namespace: str,
    task_id: str,
) -> list[SimWorldline]:
    """Create worldlines and clone the base graph into each.

    Args:
        session: SQLAlchemy sync session.
        task: The SimTask object.
        base_namespace: The base graph namespace to clone from.
        task_id: String task ID (for namespace generation).

    Returns:
        List of created SimWorldline objects.
    """
    n = task.num_timelines or 3

    # 1. Generate assumptions via LLM
    assumptions = _generate_assumptions(task, n)
    if not assumptions:
        # Fallback: create bare worldlines without LLM assumptions
        logger.warning("No assumptions generated, creating bare worldlines for task %s", task.id)
        assumptions = _default_assumptions(n)

    # Ensure we have exactly n
    assumptions = assumptions[:n]
    while len(assumptions) < n:
        assumptions.append({"assumption_type": "neutral", "title": f"世界线 {len(assumptions)+1}", "assumption": "", "key_conditions": []})

    # 2. Create worldlines + clone graph
    worldlines = []
    for i, asmp in enumerate(assumptions):
        wl_namespace = f"task_{task_id}_wl_{i}"

        wl = SimWorldline(
            task_id=task.id,
            graph_namespace=wl_namespace,
            initial_assumption=asmp.get("assumption", ""),
            assumption_type=asmp.get("assumption_type", "neutral"),
            status="pending",
        )
        session.add(wl)
        session.flush()  # get wl.id

        # 3. Clone base graph → worldline namespace
        _clone_graph(session, base_namespace, wl_namespace)

        # 4. Write initial assumption as a special fact in the worldline graph
        _write_assumption_fact(session, task, wl, asmp, wl_namespace)

        worldlines.append(wl)
        logger.info(
            "Bootstrapped worldline %s (%s) for task %s",
            wl_namespace, asmp.get("assumption_type"), task.id,
        )

    session.commit()
    return worldlines


# ---------------------------------------------------------------------------
# Graph cloning
# ---------------------------------------------------------------------------

def clone_graph(session: Session, src_namespace: str, dst_namespace: str) -> int:
    """Deep-copy all active entity_edges (and referenced entities) from src → dst namespace.

    Returns number of edges cloned.
    """
    return _clone_graph(session, src_namespace, dst_namespace)


def _clone_graph(session: Session, src_namespace: str, dst_namespace: str) -> int:
    """Internal: clone entities + edges from src namespace to dst namespace."""
    # --- Clone entities ---
    src_entities = session.execute(
        select(Entity).where(Entity.group_id == src_namespace)
    ).scalars().all()

    entity_id_map: dict[uuid.UUID, uuid.UUID] = {}  # old_id → new_id

    for src_ent in src_entities:
        new_ent = Entity(
            group_id=dst_namespace,
            name=src_ent.name,
            entity_type=src_ent.entity_type,
            summary=src_ent.summary,
            summary_embedding=src_ent.summary_embedding,
            display_name=src_ent.display_name,
            metadata_=src_ent.metadata_,
        )
        session.add(new_ent)
        session.flush()
        entity_id_map[src_ent.id] = new_ent.id

    # --- Clone edges (only active: expired_at IS NULL) ---
    src_edges = session.execute(
        select(EntityEdge).where(
            EntityEdge.group_id == src_namespace,
            EntityEdge.expired_at.is_(None),
        )
    ).scalars().all()

    cloned = 0
    for src_edge in src_edges:
        new_src_id = entity_id_map.get(src_edge.source_entity_id)
        new_tgt_id = entity_id_map.get(src_edge.target_entity_id)
        if new_src_id is None or new_tgt_id is None:
            logger.warning("Skipping edge %s: entity not mapped during clone", src_edge.id)
            continue

        new_edge = EntityEdge(
            group_id=dst_namespace,
            source_entity_id=new_src_id,
            target_entity_id=new_tgt_id,
            predicate=src_edge.predicate,
            fact=src_edge.fact,
            fact_embedding=src_edge.fact_embedding,
            valid_at=src_edge.valid_at,
            expired_at=None,
            episode_ids=list(src_edge.episode_ids or []),
            generated_by="bootstrap",
            confidence=src_edge.confidence,
        )
        session.add(new_edge)
        cloned += 1

    session.flush()
    logger.info("Cloned %d edges from %s → %s", cloned, src_namespace, dst_namespace)
    return cloned


# ---------------------------------------------------------------------------
# Write assumption as initial fact
# ---------------------------------------------------------------------------

def _write_assumption_fact(
    session: Session,
    task: SimTask,
    wl: SimWorldline,
    asmp: dict,
    wl_namespace: str,
) -> None:
    """Write the worldline's initial assumption as a synthetic fact edge."""
    if not asmp.get("assumption"):
        return

    assumption_text = asmp["assumption"]
    assumption_type = asmp.get("assumption_type", "neutral")

    # Represent assumption as a triplet: task_goal --initial_assumption--> worldline_type
    triplet = Triplet(
        subject=task.goal or task.title,
        subject_type="concept",
        predicate="initial_assumption",
        object=assumption_type,
        object_type="concept",
        fact=assumption_text[:500],  # truncate for storage
        confidence=1.0,
    )

    try:
        # Use task.created_at as valid_at (start of simulation)
        # episode_id: use worldline id as a synthetic episode reference
        temporal_upsert(
            session=session,
            group_id=wl_namespace,
            triplet=triplet,
            fact_embedding=None,  # no embedding for bootstrap assumptions
            episode_id=wl.id,  # repurpose worldline ID as episode ref
            valid_at=task.created_at or datetime.utcnow(),
            generated_by="bootstrap",
            confidence=1.0,
        )
    except Exception:
        logger.exception("Failed to write assumption fact for worldline %s", wl.id)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _generate_assumptions(task: SimTask, n: int) -> list[dict]:
    """Call LLM to generate n differentiated worldline assumptions."""
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    scene_cfg = get_scene(task.scene_type or "geopolitics")

    system_prompt = ASSUMPTION_SYSTEM_PROMPT.format(n=n)
    user_message = (
        f"Scene: {scene_cfg['display_name']}\n"
        f"Goal: {task.goal or task.title}\n\n"
        f"Background summary (first 2000 chars):\n{task.seed_content[:2000]}"
    )

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"```", "", raw).strip()

        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("assumptions", data.get("worldlines", []))
        if not isinstance(data, list):
            logger.warning("LLM returned non-list for assumptions: %s", raw[:200])
            return []
        return data
    except Exception:
        logger.exception("Assumption generation failed for task %s", task.id)
        return []


def _default_assumptions(n: int) -> list[dict]:
    """Fallback assumptions when LLM fails."""
    types = ["optimistic", "neutral", "pessimistic"]
    result = []
    for i in range(n):
        t = types[i % len(types)]
        result.append({
            "assumption_type": t,
            "title": f"{t.capitalize()} Scenario",
            "assumption": f"Initial {t} scenario for this simulation.",
            "key_conditions": [],
        })
    return result
