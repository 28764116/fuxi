"""Report generation for multi-worldline simulation.

generate_worldline_reports:
  - 为每条世界线生成详情报告（事件流摘要、关键转折、Agent走向、评分依据）
  - 生成1份总报告（横向对比所有世界线）
  - 写入 sim_reports 表

Legacy generate_report retained for backward compat.
"""

import json
import logging
import re

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from simulation.models import SimAgent, SimReport, SimTask, SimWorldline, SimWorldlineEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

WORLDLINE_REPORT_PROMPT = """\
You are a strategic simulation analyst. Write a detailed analysis report in Chinese Markdown \
for ONE simulated worldline.

The report must include these sections:
1. **世界线概述** — 初始假设、类型（乐观/中性/悲观）、最终评分和判定（水上/水下）
2. **关键事件流** — 按时间顺序列举5-10个最重要事件，说明其影响
3. **关键转折点** — 2-3个扭转走势的决定性时刻
4. **主要行为体走向** — 重要 Agent 的行动轨迹与立场变化
5. **评分分析** — 各维度得分的解读与原因
6. **结论** — 这条世界线说明了什么，有何启示

Keep the report analytical and fact-grounded. Write in professional Chinese.
"""

SUMMARY_REPORT_PROMPT = """\
You are a strategic simulation analyst. Write a comprehensive SUMMARY report in Chinese Markdown \
that compares ALL worldlines of a multi-world simulation.

The report must include:
1. **推演总览** — 任务目标、场景类型、世界线数量、整体结论
2. **世界线横向对比** — 各世界线的核心假设、最终走势、评分排名
3. **共同规律** — 跨世界线出现的共同趋势或必然结果
4. **分叉点分析** — 哪些关键决策导致了世界线的分化
5. **最优路径建议** — 基于推演，什么条件/策略更有可能达成好结果
6. **风险警示** — 需要特别关注的下行风险

Write in professional Chinese, be analytical and decision-relevant.
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def generate_worldline_reports(session: Session, task: SimTask) -> None:
    """Generate per-worldline reports + one summary report, persist to sim_reports."""
    worldlines = session.execute(
        select(SimWorldline).where(SimWorldline.task_id == task.id)
        .order_by(SimWorldline.score.desc().nulls_last())
    ).scalars().all()

    agents = session.execute(
        select(SimAgent).where(SimAgent.task_id == task.id)
        .order_by(SimAgent.influence_weight.desc())
    ).scalars().all()
    agent_map = {str(a.id): a.name for a in agents}

    wl_summaries = []  # collected for summary report

    for wl in worldlines:
        try:
            content, summary = _generate_worldline_report(session, task, wl, agent_map)
            report = SimReport(
                task_id=task.id,
                worldline_id=wl.id,
                title=f"{task.title} — {wl.assumption_type} 世界线报告",
                content=content,
                report_type="worldline",
            )
            session.add(report)
            wl_summaries.append(summary)
            logger.info("Generated worldline report for %s", wl.graph_namespace)
        except Exception:
            logger.exception("Failed to generate report for worldline %s", wl.id)

    # Generate summary / comparison report
    try:
        summary_content = _generate_summary_report(task, wl_summaries)
        summary_report = SimReport(
            task_id=task.id,
            worldline_id=None,
            title=f"{task.title} — 推演总报告",
            content=summary_content,
            report_type="summary",
        )
        session.add(summary_report)
        logger.info("Generated summary report for task %s", task.id)
    except Exception:
        logger.exception("Failed to generate summary report for task %s", task.id)

    session.commit()


# ---------------------------------------------------------------------------
# Per-worldline report
# ---------------------------------------------------------------------------

def _generate_worldline_report(
    session: Session,
    task: SimTask,
    wl: SimWorldline,
    agent_map: dict[str, str],
) -> tuple[str, dict]:
    """Generate report for one worldline. Returns (markdown_content, summary_dict)."""

    # Fetch events ordered by step
    events = session.execute(
        select(SimWorldlineEvent)
        .where(SimWorldlineEvent.worldline_id == wl.id)
        .order_by(SimWorldlineEvent.step_index.asc(), SimWorldlineEvent.impact_score.desc())
    ).scalars().all()

    # Build event summary for LLM (cap at 40)
    events_text = "\n".join(
        f"Step {e.step_index} | {agent_map.get(str(e.agent_id), 'Unknown')} "
        f"| [{e.action_type}] {e.description} (impact={e.impact_score:.2f})"
        for e in events[:40]
    ) or "(no events)"

    score_detail_text = json.dumps(wl.score_detail or {}, ensure_ascii=False, indent=2)

    user_message = (
        f"## Task Goal\n{task.goal or task.title}\n\n"
        f"## Worldline Info\n"
        f"- Type: {wl.assumption_type}\n"
        f"- Initial Assumption: {wl.initial_assumption or '(none)'}\n"
        f"- Score: {f'{wl.score:.1f}' if wl.score is not None else 'N/A'}\n"
        f"- Verdict: {wl.verdict or 'unknown'}\n\n"
        f"## Event Timeline\n{events_text}\n\n"
        f"## Scoring Detail\n{score_detail_text}"
    )

    content = _call_llm(WORLDLINE_REPORT_PROMPT, user_message)
    if not content:
        content = (
            f"# {task.title} — {wl.assumption_type} 世界线\n\n"
            f"评分：{f'{wl.score:.1f}' if wl.score else 'N/A'}  判定：{wl.verdict}\n\n报告生成失败。"
        )

    # Build summary dict for comparison report
    summary = {
        "assumption_type": wl.assumption_type,
        "initial_assumption": (wl.initial_assumption or "")[:300],
        "score": wl.score,
        "verdict": wl.verdict,
        "event_count": len(events),
        "top_events": [
            f"[{e.action_type}] {e.description[:100]}"
            for e in sorted(events, key=lambda x: x.impact_score, reverse=True)[:5]
        ],
        "score_detail": wl.score_detail or {},
    }
    return content, summary


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def _generate_summary_report(task: SimTask, wl_summaries: list[dict]) -> str:
    summaries_text = json.dumps(wl_summaries, ensure_ascii=False, indent=2)
    user_message = (
        f"## Task Goal\n{task.goal or task.title}\n\n"
        f"## Scene Type\n{task.scene_type or 'geopolitics'}\n\n"
        f"## Worldline Summaries\n{summaries_text}"
    )

    content = _call_llm(SUMMARY_REPORT_PROMPT, user_message)
    if not content:
        content = f"# {task.title} — 推演总报告\n\n报告生成失败。"
    return content


# ---------------------------------------------------------------------------
# LLM helper
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
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        logger.info("Report generated: %d chars", len(raw))
        return raw
    except Exception:
        logger.exception("Report generation LLM call failed")
        return ""


# ---------------------------------------------------------------------------
# Legacy API
# ---------------------------------------------------------------------------

def generate_report(task_title: str, sim_result: dict) -> str:
    """[Legacy] Generate a markdown report from OASIS simulation results."""
    LEGACY_PROMPT = """\
You are a professional social media simulation analyst. Based on the simulation results below, \
generate a comprehensive analysis report in Markdown format (in Chinese).
The report should include: 概述、舆情走势、阵营分析、关键意见领袖、传播路径、结论与建议.
Simulation Results:
"""
    summary = {
        "title": task_title,
        "num_agents": sim_result.get("num_agents"),
        "total_posts": sim_result.get("total_posts"),
        "sample_posts": sim_result.get("posts", [])[:20],
        "profiles": sim_result.get("profiles", [])[:10],
    }
    content = _call_llm(
        LEGACY_PROMPT,
        json.dumps(summary, ensure_ascii=False, indent=2),
    )
    return content or f"# {task_title}\n\n报告生成失败，请重试。"
