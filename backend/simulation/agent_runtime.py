"""Agent single-step execution runtime.

run_agent_step:
  构建 prompt（场景前缀 + 三层画像 + 事实列表 + 待响应事件 + action_types）
  → 调用 LLM
  → 返回结构化 AgentAction
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openai import OpenAI

from app.config import settings
from simulation.models import SimAgent
from simulation.scene_registry import get_action_types, get_prompt_prefix

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentAction:
    agent_id: str
    agent_name: str
    action_type: str                        # 必须在 scene action_types 内
    description: str                        # 人类可读行动描述
    new_facts: list[dict] = field(default_factory=list)
    # new_facts: [{"subject": .., "predicate": .., "object": .., "fact": .., "confidence": ..}]
    confidence: float = 0.8
    impact_score: float = 0.0               # 0-1，由 LLM 自评
    reasoning: str = ""                     # 内部推理（可选，调试用）


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

AGENT_STEP_SYSTEM = """\
{scene_prefix}

You are simulating a specific actor in this scenario. Your task is to decide ONE action \
for this actor in the current simulation step, based on:
1. Your actor profile (who you are, your goals, personality)
2. The current known facts visible to you
3. Any pending events that require your response
4. The available action types for this scenario

RESPONSE FORMAT — return ONLY a JSON object:
{{
  "action_type": "<one of the allowed action types>",
  "description": "<1-3 sentence description of what this actor does and why>",
  "new_facts": [
    {{
      "subject": "<entity name>",
      "subject_type": "<person|organization|concept|event|policy|...>",
      "predicate": "<relationship>",
      "object": "<entity name>",
      "object_type": "<type>",
      "fact": "<one sentence natural language>",
      "confidence": <float 0-1>
    }}
  ],
  "confidence": <float 0-1, your confidence in this decision>,
  "impact_score": <float 0-1, estimated impact on the overall scenario>,
  "reasoning": "<brief internal reasoning, 1-2 sentences>"
}}

new_facts should contain any new factual assertions this action creates or reveals.
If this action creates no new facts, set new_facts to [].
"""

AGENT_STEP_USER = """\
## Actor Profile
Name: {name}
Role: {role}
Background: {background}
Personality: {personality}
Ideology / Stance: {ideology}
Influence weight: {influence_weight:.2f}
Risk tolerance: {risk_tolerance:.2f}
Information access: {information_access}

## Current Known Facts (your information view)
{facts_text}

## Pending Events Requiring Response
{pending_text}

## Allowed Action Types
{action_types_text}

## Simulation Context
Time step: {sim_time}
Scenario goal: {goal}

Decide your action now.
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def run_agent_step(
    agent: SimAgent,
    facts: list[str],
    pending_reactions: list[dict],
    scene_type: str,
    sim_time: datetime | None,
    goal: str = "",
) -> AgentAction:
    """Execute one simulation step for an agent.

    Args:
        agent: The SimAgent ORM object.
        facts: List of fact strings visible to this agent (filtered by information_access).
        pending_reactions: List of pending event dicts from previous high-impact actions.
        scene_type: Scene type key (e.g. 'geopolitics').
        sim_time: Current simulation time.
        goal: The task's overall analytical goal.

    Returns:
        An AgentAction dataclass with structured output.
    """
    scene_prefix = get_prompt_prefix(scene_type)
    action_types = get_action_types(scene_type)

    scene_meta = agent.scene_metadata or {}
    info_access = scene_meta.get("information_access", "partial")

    # Build facts text (cap at 30 facts to avoid token overflow)
    facts_display = facts[:30]
    facts_text = "\n".join(f"- {f}" for f in facts_display) if facts_display else "(no facts available)"

    # Build pending reactions text
    if pending_reactions:
        pending_text = "\n".join(
            f"- [{p.get('action_type', 'event')}] {p.get('description', '')}"
            for p in pending_reactions[:10]
        )
    else:
        pending_text = "(none)"

    action_types_text = ", ".join(action_types)
    sim_time_str = sim_time.isoformat() if sim_time else "unknown"

    system_prompt = AGENT_STEP_SYSTEM.format(scene_prefix=scene_prefix)
    user_message = AGENT_STEP_USER.format(
        name=agent.name,
        role=agent.role or "Unknown",
        background=agent.background or "No background available",
        personality=agent.personality or "Neutral",
        ideology=agent.ideology or "Unspecified",
        influence_weight=agent.influence_weight,
        risk_tolerance=agent.risk_tolerance,
        information_access=info_access,
        facts_text=facts_text,
        pending_text=pending_text,
        action_types_text=action_types_text,
        sim_time=sim_time_str,
        goal=goal or "(not specified)",
    )

    raw_action = _call_llm(system_prompt, user_message)
    return _parse_action(raw_action, agent, action_types)


# ---------------------------------------------------------------------------
# LLM call + parser
# ---------------------------------------------------------------------------

def _call_llm(system_prompt: str, user_message: str) -> str:
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.6,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"```", "", raw).strip()
        return raw
    except Exception:
        logger.exception("LLM call failed in agent_runtime")
        return ""


def _parse_action(raw: str, agent: SimAgent, valid_action_types: list[str]) -> AgentAction:
    """Parse LLM JSON output into AgentAction, with graceful fallback."""
    fallback = AgentAction(
        agent_id=str(agent.id),
        agent_name=agent.name,
        action_type="observe",
        description=f"{agent.name} 选择观望，暂不行动。",
        new_facts=[],
        confidence=0.5,
        impact_score=0.0,
    )

    if not raw:
        return fallback

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Agent %s: failed to parse LLM JSON: %s", agent.name, raw[:200])
        return fallback

    action_type = str(data.get("action_type", "observe")).strip().lower()
    # Validate action_type against scene registry
    if action_type not in valid_action_types:
        logger.warning(
            "Agent %s returned invalid action_type '%s', falling back to 'observe'",
            agent.name, action_type,
        )
        action_type = "observe"

    new_facts_raw = data.get("new_facts", [])
    if not isinstance(new_facts_raw, list):
        new_facts_raw = []

    return AgentAction(
        agent_id=str(agent.id),
        agent_name=agent.name,
        action_type=action_type,
        description=str(data.get("description", "")).strip(),
        new_facts=new_facts_raw,
        confidence=_clamp(data.get("confidence", 0.8)),
        impact_score=_clamp(data.get("impact_score", 0.0)),
        reasoning=str(data.get("reasoning", "")).strip(),
    )


def _clamp(val: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return 0.5
