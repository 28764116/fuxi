"""Report generation from simulation results using LLM."""

import json
import logging
import re

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

REPORT_PROMPT = """\
You are a professional social media simulation analyst. Based on the simulation results below, \
generate a comprehensive analysis report in Markdown format (in Chinese).

The report should include:
1. **概述** — 仿真主题、参数（Agent数量、轮数）、总体数据
2. **舆情走势** — 各轮次的讨论热度变化、关键转折点
3. **阵营分析** — 不同立场的分布、各方核心观点
4. **关键意见领袖** — 最活跃、最有影响力的 Agent
5. **传播路径** — 信息如何在群体中扩散
6. **结论与建议** — 基于仿真结果的洞察

Simulation Results:
"""


def generate_report(task_title: str, sim_result: dict) -> str:
    """Generate a markdown report from simulation results."""
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    # Prepare a summary of results to avoid token overflow
    summary = {
        "title": task_title,
        "num_agents": sim_result.get("num_agents"),
        "num_rounds": sim_result.get("num_rounds"),
        "total_posts": sim_result.get("total_posts"),
        "total_interactions": sim_result.get("total_interactions"),
        "sample_posts": sim_result.get("posts", [])[:30],
        "sample_interactions": sim_result.get("interactions", [])[:20],
        "profiles": sim_result.get("profiles", [])[:20],
    }

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": REPORT_PROMPT},
                {"role": "user", "content": json.dumps(summary, ensure_ascii=False, indent=2)},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        logger.info("Report generated: %d chars", len(raw))
        return raw
    except Exception:
        logger.exception("Report generation failed")
        return f"# {task_title}\n\n报告生成失败，请重试。"
