"""Simulation engine wrapping OASIS social media simulation.

This module provides a synchronous interface for Celery workers
to run OASIS simulations and collect results.
"""

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def build_agent_profiles(seed_content: str, num_agents: int) -> list[dict]:
    """Use LLM to generate diverse agent profiles from seed material."""
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

Example output format:
[
  {{"name": "用户A", "bio": "科技行业从业者", "personality": "理性、数据驱动", "stance": "支持"}},
  {{"name": "用户B", "bio": "在校大学生", "personality": "热情、理想主义", "stance": "反对"}}
]
"""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = raw.strip()
        profiles = json.loads(raw)
        if isinstance(profiles, dict):
            profiles = profiles.get("profiles", profiles.get("users", []))
        logger.info("Generated %d agent profiles", len(profiles))
        return profiles[:num_agents]
    except Exception:
        logger.exception("Failed to generate agent profiles")
        # Fallback: generate generic profiles
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
    """Run an OASIS social media simulation.

    Args:
        seed_content: The seed topic/material.
        profiles: Agent profiles.
        num_rounds: Number of simulation rounds.
        scenario: Simulation type.
        on_round_complete: Callback(round_num, total_rounds, round_data) for progress.

    Returns:
        dict with simulation results (posts, interactions, timeline).
    """
    logger.info(
        "Starting simulation: %d agents, %d rounds, scenario=%s",
        len(profiles), num_rounds, scenario,
    )

    all_posts = []
    all_interactions = []

    for round_num in range(1, num_rounds + 1):
        round_posts, round_interactions = _simulate_round(
            seed_content, profiles, round_num, all_posts
        )
        all_posts.extend(round_posts)
        all_interactions.extend(round_interactions)

        if on_round_complete:
            on_round_complete(round_num, num_rounds, {
                "posts": len(round_posts),
                "interactions": len(round_interactions),
            })

    result = {
        "num_agents": len(profiles),
        "num_rounds": num_rounds,
        "total_posts": len(all_posts),
        "total_interactions": len(all_interactions),
        "posts": all_posts,
        "interactions": all_interactions,
        "profiles": profiles,
    }

    logger.info(
        "Simulation complete: %d posts, %d interactions",
        len(all_posts), len(all_interactions),
    )
    return result


def _simulate_round(
    seed_content: str,
    profiles: list[dict],
    round_num: int,
    existing_posts: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Simulate one round of social media activity using LLM."""
    import json
    import re

    from openai import OpenAI

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    # Select a subset of agents to be active this round
    import random
    active_count = min(len(profiles), max(3, len(profiles) // 3))
    active_agents = random.sample(profiles, active_count)

    # Build context from recent posts
    recent_posts = existing_posts[-10:] if existing_posts else []
    posts_context = ""
    if recent_posts:
        posts_context = "\nRecent posts on the platform:\n" + "\n".join(
            f"- {p['author']}: {p['content']}" for p in recent_posts
        )

    agent_list = "\n".join(
        f"- {a['name']} ({a['bio']}, {a['personality']}, stance: {a['stance']})"
        for a in active_agents
    )

    prompt = f"""\
Simulate Round {round_num} of a social media discussion.

Topic: {seed_content[:1000]}
{posts_context}

Active users this round:
{agent_list}

For each active user, generate 1 post (and optionally 1 reply to an existing post).
Each user should act according to their personality and stance.

Return ONLY a JSON object with:
- "posts": [{{"author": "name", "content": "post text", "type": "original|reply", "reply_to": "author name or null"}}]
- "interactions": [{{"from": "name", "to": "name", "type": "like|reply|repost"}}]
"""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = raw.strip()
        data = json.loads(raw)

        posts = data.get("posts", [])
        interactions = data.get("interactions", [])

        # Tag with round number
        for p in posts:
            p["round"] = round_num
        for i in interactions:
            i["round"] = round_num

        return posts, interactions

    except Exception:
        logger.exception("Round %d simulation failed", round_num)
        return [], []
