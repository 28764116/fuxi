"""Simulation engine: worldline simulation loop.

run_worldline:
  - 按 influence_weight 排序 Agent
  - 按 information_access 过滤图谱事实
  - 调用 agent_runtime.run_agent_step
  - new_facts 写回图谱（generated_by='agent_action'）
  - 写 sim_worldline_events
  - 高影响力事件（impact_score >= 0.7）推入相关 Agent 的 pending_reactions
  - 步末保存 sim_checkpoints

Legacy functions (build_agent_profiles / run_simulation) retained for backward compat.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from simulation.models import SimAgent, SimCheckpoint, SimTask, SimWorldline, SimWorldlineEvent

logger = logging.getLogger(__name__)

# 影响力阈值：高于此值的事件推入其他 Agent 的 pending_reactions
HIGH_IMPACT_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_worldline(session: Session, task: SimTask, worldline: SimWorldline) -> None:
    """Run the full simulation loop for a single worldline.

    Steps per time step:
      1. Sort agents by influence_weight DESC
      2. For each agent: filter facts by information_access → run_agent_step
      3. Write new_facts to graph (temporal_upsert, generated_by='agent_action')
      4. Write SimWorldlineEvent
      5. High-impact events → push to other agents' pending_reactions
      6. Save SimCheckpoint for each agent
    """
    from memory.embedder import get_embeddings
    from memory.extractor import Triplet
    from memory.temporal import temporal_upsert

    worldline.status = "running"
    session.flush()

    # Load agents sorted by influence_weight DESC
    agents: list[SimAgent] = list(
        session.execute(
            select(SimAgent)
            .where(SimAgent.task_id == task.id)
            .order_by(SimAgent.influence_weight.desc())
        ).scalars().all()
    )

    if not agents:
        logger.warning("No agents found for task %s, skipping worldline %s", task.id, worldline.id)
        worldline.status = "completed"
        session.flush()
        return

    num_steps = task.num_rounds  # reuse num_rounds as step count
    scene_type = task.scene_type or "geopolitics"
    goal = task.goal or task.title

    # Initialize per-agent pending_reactions dict: agent_id → list[dict]
    pending_map: dict[uuid.UUID, list[dict]] = {a.id: [] for a in agents}

    # Determine sim time range
    sim_start = task.sim_start_time or task.created_at
    time_step_delta = _time_delta(task.time_step_unit)

    logger.info(
        "Starting worldline %s (%s): %d agents × %d steps",
        worldline.graph_namespace, worldline.assumption_type, len(agents), num_steps,
    )

    for step_idx in range(num_steps):
        sim_time = sim_start + time_step_delta * step_idx
        high_impact_events: list[dict] = []

        for agent in agents:
            # 1. Get visible facts for this agent
            facts = _get_agent_facts(session, worldline.graph_namespace, agent)

            # 2. Get pending reactions for this agent
            pending = pending_map.get(agent.id, [])

            # 3. Run agent step
            from simulation.agent_runtime import run_agent_step
            action = run_agent_step(
                agent=agent,
                facts=facts,
                pending_reactions=pending,
                scene_type=scene_type,
                sim_time=sim_time,
                goal=goal,
            )

            # 4. Write new_facts to graph
            _write_new_facts(session, action, worldline, agent, sim_time, temporal_upsert, get_embeddings, Triplet)

            # 5. Write event record
            event = SimWorldlineEvent(
                worldline_id=worldline.id,
                agent_id=agent.id,
                sim_time=sim_time,
                step_index=step_idx,
                action_type=action.action_type,
                description=action.description,
                impact_score=action.impact_score,
                new_facts=action.new_facts or [],
            )
            session.add(event)
            session.flush()

            # 6. Collect high-impact events
            if action.impact_score >= HIGH_IMPACT_THRESHOLD:
                high_impact_events.append({
                    "event_id": str(event.id),
                    "agent_name": agent.name,
                    "action_type": action.action_type,
                    "description": action.description,
                    "impact_score": action.impact_score,
                })

            # 7. Save checkpoint for this agent
            checkpoint = SimCheckpoint(
                worldline_id=worldline.id,
                agent_id=agent.id,
                step_index=step_idx,
                dynamic_state={
                    "last_action_type": action.action_type,
                    "last_impact_score": action.impact_score,
                    "confidence": action.confidence,
                },
                pending_reactions=pending,
            )
            session.add(checkpoint)

            # Clear consumed pending reactions
            pending_map[agent.id] = []

        # After all agents act: distribute high-impact events to other agents
        for evt in high_impact_events:
            for agent in agents:
                if agent.name != evt["agent_name"]:
                    pending_map[agent.id].append(evt)

        session.flush()
        logger.info(
            "Worldline %s step %d/%d complete, %d high-impact events",
            worldline.graph_namespace, step_idx + 1, num_steps, len(high_impact_events),
        )

    worldline.status = "completed"
    session.flush()
    logger.info("Worldline %s completed", worldline.graph_namespace)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent_facts(session: Session, graph_namespace: str, agent: SimAgent) -> list[str]:
    """Return fact strings visible to this agent, filtered by information_access."""
    from memory.models import EntityEdge
    from sqlalchemy import select as sa_select

    scene_meta = agent.scene_metadata or {}
    info_access = scene_meta.get("information_access", "partial")

    stmt = (
        sa_select(EntityEdge)
        .where(
            EntityEdge.group_id == graph_namespace,
            EntityEdge.expired_at.is_(None),
        )
        .order_by(EntityEdge.valid_at.desc())
    )

    # Limit by access level
    if info_access == "full":
        stmt = stmt.limit(60)
    elif info_access == "partial":
        stmt = stmt.limit(30)
    else:  # limited
        stmt = stmt.limit(15)

    edges = session.execute(stmt).scalars().all()
    return [e.fact for e in edges]


def _write_new_facts(
    session: Session,
    action: Any,
    worldline: SimWorldline,
    agent: SimAgent,
    sim_time: datetime,
    temporal_upsert: Any,
    get_embeddings: Any,
    Triplet: Any,
) -> None:
    """Write action.new_facts into the worldline's graph namespace."""
    if not action.new_facts:
        return

    valid_facts = []
    for nf in action.new_facts:
        try:
            t = Triplet(
                subject=str(nf.get("subject", "")).strip(),
                subject_type=str(nf.get("subject_type", "concept")).strip().lower(),
                predicate=str(nf.get("predicate", "related_to")).strip().lower(),
                object=str(nf.get("object", "")).strip(),
                object_type=str(nf.get("object_type", "concept")).strip().lower(),
                fact=str(nf.get("fact", "")).strip(),
                confidence=float(nf.get("confidence", 0.8)),
            )
            if t.subject and t.object and t.fact:
                valid_facts.append(t)
        except Exception:
            continue

    if not valid_facts:
        return

    fact_texts = [t.fact for t in valid_facts]
    embeddings = get_embeddings(fact_texts)
    while len(embeddings) < len(valid_facts):
        embeddings.append(None)

    for triplet, embedding in zip(valid_facts, embeddings):
        try:
            temporal_upsert(
                session=session,
                group_id=worldline.graph_namespace,
                triplet=triplet,
                fact_embedding=embedding,
                episode_id=agent.id,          # repurpose agent.id as synthetic episode ref
                valid_at=sim_time,
                generated_by="agent_action",
                confidence=triplet.confidence,
            )
        except Exception:
            logger.exception(
                "Failed to upsert fact '%s' for agent %s in worldline %s",
                triplet.fact[:80], agent.name, worldline.graph_namespace,
            )


def _time_delta(unit: str) -> timedelta:
    """Convert time_step_unit string to timedelta."""
    mapping = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30),
    }
    return mapping.get(unit, timedelta(days=1))


# ---------------------------------------------------------------------------
# Legacy API (kept for backward compat, not used in new pipeline)
# ---------------------------------------------------------------------------

def build_agent_profiles(seed_content: str, num_agents: int) -> list[dict]:
    """[Legacy] Use LLM to generate diverse agent profiles from seed material."""
    import json
    import re
    from openai import OpenAI

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    prompt = f"""\
Based on the following seed material, generate {num_agents} diverse social media user profiles.
Each profile should have: name, bio (1-2 sentences), personality traits, stance on the topic.
Return ONLY a JSON array.

Seed material:
{seed_content[:2000]}
"""
    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw).strip()
        profiles = json.loads(raw)
        if isinstance(profiles, dict):
            profiles = profiles.get("profiles", profiles.get("users", []))
        return profiles[:num_agents]
    except Exception:
        logger.exception("Failed to generate agent profiles")
        return [
            {"name": f"用户{i+1}", "bio": "普通用户", "personality": "中立", "stance": "观望"}
            for i in range(num_agents)
        ]


def run_simulation(
    seed_content: str,
    profiles: list[dict],
    num_rounds: int,
    scenario: str,
    on_round_complete: Any = None,
) -> dict:
    """[Legacy] Run OASIS-style social media simulation."""
    import json
    import re
    import random
    from openai import OpenAI

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    all_posts: list[dict] = []
    all_interactions: list[dict] = []

    for round_num in range(1, num_rounds + 1):
        active_count = min(len(profiles), max(3, len(profiles) // 3))
        active_agents = random.sample(profiles, active_count)
        recent_posts = all_posts[-10:]
        posts_ctx = "\n".join(f"- {p['author']}: {p['content']}" for p in recent_posts)
        agent_list = "\n".join(
            f"- {a['name']} ({a.get('bio','')}, {a.get('personality','')}, stance: {a.get('stance','')})"
            for a in active_agents
        )
        prompt = f"Simulate Round {round_num}.\nTopic: {seed_content[:800]}\nRecent posts:\n{posts_ctx}\nActive users:\n{agent_list}\nReturn JSON with 'posts' and 'interactions'."
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
            )
            raw = resp.choices[0].message.content or ""
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
            raw = re.sub(r"```(?:json)?\s*\n?", "", raw).strip()
            data = json.loads(raw)
            rp = data.get("posts", [])
            ri = data.get("interactions", [])
            for x in rp:
                x["round"] = round_num
            for x in ri:
                x["round"] = round_num
            all_posts.extend(rp)
            all_interactions.extend(ri)
        except Exception:
            logger.exception("Round %d simulation failed", round_num)

        if on_round_complete:
            on_round_complete(round_num, num_rounds, {"posts": len(all_posts), "interactions": len(all_interactions)})

    return {
        "num_agents": len(profiles), "num_rounds": num_rounds,
        "total_posts": len(all_posts), "total_interactions": len(all_interactions),
        "posts": all_posts, "interactions": all_interactions, "profiles": profiles,
    }
