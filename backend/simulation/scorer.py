"""Worldline scorer: evaluate each worldline after simulation completes.

按场景的 scoring_metrics 对每条世界线打分（0-100），输出各维度明细，
写回 sim_worldlines.score、score_detail、verdict。

verdict:
  above_water  — 总分 >= 60（正面/可控）
  below_water  — 总分 < 40（负面/失控）
  neutral      — 40 <= 总分 < 60
"""

import json
import logging
import re

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from simulation.models import SimTask, SimWorldline, SimWorldlineEvent
from simulation.scene_registry import get_scoring_metrics

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """\
You are an expert scenario analyst evaluating a simulated worldline.

You will receive:
1. The simulation goal
2. The worldline's initial assumption
3. A summary of key events that occurred
4. Scoring dimensions with weights

Score each dimension from 0-100, then compute a weighted total.
For dimensions marked as "reverse" (逆向), a LOWER raw value in the simulation = HIGHER score.

Return ONLY a JSON object:
{{
  "scores": {{
    "<dimension_key>": {{
      "score": <int 0-100>,
      "rationale": "<1-2 sentence explanation>"
    }},
    ...
  }},
  "total_score": <float, weighted sum>,
  "verdict": "above_water|neutral|below_water",
  "summary": "<2-3 sentence overall assessment>"
}}
"""


def score_worldlines(session: Session, task: SimTask) -> None:
    """Score all worldlines for a task and write results back."""
    worldlines = session.execute(
        select(SimWorldline).where(SimWorldline.task_id == task.id)
    ).scalars().all()

    for wl in worldlines:
        try:
            _score_one_worldline(session, task, wl)
        except Exception:
            logger.exception("Failed to score worldline %s", wl.id)

    session.commit()


def _score_one_worldline(session: Session, task: SimTask, wl: SimWorldline) -> None:
    """Score a single worldline."""
    scene_type = task.scene_type or "geopolitics"
    metrics = get_scoring_metrics(scene_type)

    # Collect event summary (last 30 high-impact events for context)
    events = session.execute(
        select(SimWorldlineEvent)
        .where(SimWorldlineEvent.worldline_id == wl.id)
        .order_by(SimWorldlineEvent.impact_score.desc())
        .limit(30)
    ).scalars().all()

    events_summary = "\n".join(
        f"- [{e.action_type}] {e.description} (impact={e.impact_score:.2f})"
        for e in events
    ) or "(no events recorded)"

    # Build metrics description for prompt
    metrics_text = "\n".join(
        f"- {key}: {v['desc']} (weight={v['weight']:.0%})"
        for key, v in metrics.items()
    )

    user_message = (
        f"## Simulation Goal\n{task.goal or task.title}\n\n"
        f"## Worldline Initial Assumption ({wl.assumption_type})\n"
        f"{wl.initial_assumption or '(not specified)'}\n\n"
        f"## Key Events Summary\n{events_summary}\n\n"
        f"## Scoring Dimensions\n{metrics_text}"
    )

    result = _call_llm_for_score(user_message)

    if not result:
        logger.warning("Scorer returned empty for worldline %s, using default", wl.id)
        result = {
            "scores": {},
            "total_score": 50.0,
            "verdict": "neutral",
            "summary": "评分失败，使用默认中性分数。",
        }

    total = result.get("total_score", 50.0)
    verdict_raw = str(result.get("verdict", "neutral")).lower()
    if verdict_raw not in ("above_water", "below_water", "neutral"):
        # Derive from score
        if total >= 60:
            verdict_raw = "above_water"
        elif total < 40:
            verdict_raw = "below_water"
        else:
            verdict_raw = "neutral"

    wl.score = float(total)
    wl.score_detail = result
    wl.verdict = verdict_raw

    logger.info(
        "Worldline %s scored: %.1f (%s)",
        wl.graph_namespace, wl.score, wl.verdict,
    )


def _call_llm_for_score(user_message: str) -> dict:
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"```", "", raw).strip()
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Scoring LLM call failed")
        return {}
