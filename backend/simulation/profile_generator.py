"""Agent profile generator.

从知识图谱中读取已提取的实体节点，通过 LLM 推断三层画像，写入 sim_agents 表。

三层画像：
  静态层  : name, role, background, personality, ideology
  动态参数层: influence_weight, risk_tolerance, change_resistance
  场景元数据层: scene_metadata (含 information_access 等)
"""

import json
import logging
import re

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from memory.models import Entity
from simulation.models import SimAgent, SimTask
from simulation.scene_registry import get_scene

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PROFILE_SYSTEM_PROMPT = """\
You are an AI agent profiler for multi-agent simulation.
Given a list of entities extracted from background material, \
generate a realistic agent profile for EACH entity that is a plausible actor \
(person, organization, government body, or significant institution).

Skip entities that are purely abstract concepts, locations, or time references.

For each actor, return a JSON object with these fields:
{
  "entity_name": "<exact name from input>",
  "role": "<job title / institutional role, one line>",
  "background": "<2-3 sentence background summary>",
  "personality": "<brief personality / decision-making style>",
  "ideology": "<worldview / stance, one line>",
  "influence_weight": <float 0.0-1.0, how influential this actor is>,
  "risk_tolerance": <float 0.0-1.0, willingness to take risk>,
  "change_resistance": <float 0.0-1.0, resistance to change>,
  "information_access": "<full | partial | limited>",
  "scene_metadata": { <any additional scene-relevant attributes as key-value> }
}

Return a JSON array of profile objects. Return ONLY the JSON array, no other text.
"""

PROFILE_SCENE_SUFFIX = """\

SCENE CONTEXT: This simulation is about {scene_display_name}.
Scene goal: {goal}
Calibrate influence_weight, risk_tolerance, and scene_metadata to fit this context.
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def generate_profiles(session: Session, task: SimTask, base_namespace: str) -> list[SimAgent]:
    """Generate SimAgent profiles from graph entities and persist them.

    Args:
        session: SQLAlchemy sync session.
        task: The SimTask object.
        base_namespace: The graph_namespace for this task's base graph.

    Returns:
        List of created SimAgent objects.
    """
    # 1. Load entities from base namespace
    entities = session.execute(
        select(Entity).where(Entity.group_id == base_namespace)
    ).scalars().all()

    if not entities:
        logger.warning("No entities found in namespace %s, skipping profiling", base_namespace)
        return []

    # Limit to top N by relevance (naive: just take all up to 30)
    entities = entities[:30]
    entity_names = [e.name for e in entities]
    entity_map = {e.name: e for e in entities}

    logger.info("Generating profiles for %d entities (task %s)", len(entities), task.id)

    # 2. Build prompt
    scene_cfg = get_scene(task.scene_type or "geopolitics")
    system_prompt = PROFILE_SYSTEM_PROMPT + PROFILE_SCENE_SUFFIX.format(
        scene_display_name=scene_cfg["display_name"],
        goal=task.goal or "通用推演",
    )

    entity_list_text = "\n".join(
        f"- {e.name} ({e.entity_type})" + (f": {e.summary[:120]}" if e.summary else "")
        for e in entities
    )
    user_message = (
        f"Background material goal: {task.goal or '(unspecified)'}\n\n"
        f"Entities to profile:\n{entity_list_text}"
    )

    # 3. Call LLM
    raw_profiles = _call_llm_for_profiles(system_prompt, user_message)
    if not raw_profiles:
        logger.warning("LLM returned no profiles for task %s", task.id)
        return []

    # 4. Persist as SimAgent rows
    agents = []
    existing_names = set()

    for p in raw_profiles:
        name = str(p.get("entity_name", "")).strip()
        if not name or name in existing_names:
            continue
        existing_names.add(name)

        entity = entity_map.get(name)

        scene_meta = p.get("scene_metadata", {}) or {}
        scene_meta["information_access"] = p.get("information_access", "partial")

        agent = SimAgent(
            task_id=task.id,
            entity_id=entity.id if entity else None,
            name=name,
            role=str(p.get("role", "")).strip() or None,
            background=str(p.get("background", "")).strip() or None,
            personality=str(p.get("personality", "")).strip() or None,
            ideology=str(p.get("ideology", "")).strip() or None,
            influence_weight=_clamp(p.get("influence_weight", 0.5)),
            risk_tolerance=_clamp(p.get("risk_tolerance", 0.5)),
            change_resistance=_clamp(p.get("change_resistance", 0.5)),
            scene_metadata=scene_meta,
        )
        session.add(agent)
        agents.append(agent)

    session.flush()
    logger.info("Created %d SimAgent records for task %s", len(agents), task.id)
    return agents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_llm_for_profiles(system_prompt: str, user_message: str) -> list[dict]:
    """Call LLM and parse profile JSON array."""
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"```", "", raw).strip()

        data = json.loads(raw)
        if isinstance(data, dict):
            # Some LLMs wrap in {"profiles": [...]}
            data = data.get("profiles", data.get("agents", []))
        if not isinstance(data, list):
            logger.warning("LLM returned non-list for profiles: %s", raw[:200])
            return []
        return data
    except Exception:
        logger.exception("Profile generation LLM call failed")
        return []


def _clamp(val, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return 0.5
