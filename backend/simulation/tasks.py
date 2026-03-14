"""Celery tasks for the simulation pipeline.

Pipeline:
  pending → extracting → profiling → bootstrapping → simulating → scoring → reporting → completed
  Any state → failed
"""

import logging
import uuid

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="simulation.run_pipeline")
def run_pipeline(task_id: str) -> None:
    """Execute the full simulation pipeline for a task.

    Steps:
      Phase 1 (0%-20%)  : extracting   — Extract entities → base graph_namespace
      Phase 2 (20%-30%) : profiling    — Generate SimAgent profiles from graph
      Phase 3 (30%-35%) : bootstrapping — Initialize worldlines with LLM assumptions
      Phase 4 (35%-85%) : simulating   — Run worldline simulation (chord)
      Phase 5 (85%-100%): scoring+reporting — Score + generate reports
    """
    from app.database import sync_session_factory
    from simulation.models import SimReport, SimTask
    from simulation.progress import publish_progress

    logger.info("Pipeline started for task %s", task_id)

    with sync_session_factory() as session:
        task = session.get(SimTask, uuid.UUID(task_id))
        if not task:
            logger.error("Task %s not found", task_id)
            return

        try:
            # === Phase 1: Entity extraction → base graph_namespace ===
            base_namespace = f"task_{task_id}_base"
            _update_task(session, task, "extracting", 5, "正在从种子材料中提取实体关系...")
            publish_progress(task_id, "extracting", 5, "正在提取实体关系...")

            _run_extraction(session, task, base_namespace)

            _update_task(session, task, "extracting", 20, "实体关系提取完成")
            publish_progress(task_id, "extracting", 20, "实体关系提取完成")

            # === Phase 2: Agent profile generation ===
            _update_task(session, task, "profiling", 22, "正在生成 Agent 画像...")
            publish_progress(task_id, "profiling", 22, "正在生成 Agent 画像...")

            _run_profiling(session, task, base_namespace)

            _update_task(session, task, "profiling", 30, "Agent 画像生成完成")
            publish_progress(task_id, "profiling", 30, "Agent 画像生成完成")

            # === Phase 3: Worldline bootstrapping ===
            _update_task(session, task, "bootstrapping", 31, "正在初始化世界线...")
            publish_progress(task_id, "bootstrapping", 31, "正在初始化世界线...")

            _run_bootstrapping(session, task, base_namespace, task_id)

            _update_task(session, task, "bootstrapping", 35, "世界线初始化完成")
            publish_progress(task_id, "bootstrapping", 35, "世界线初始化完成")

            # === Phase 4: Worldline simulation ===
            _update_task(session, task, "simulating", 36, "正在推演世界线...")
            publish_progress(task_id, "simulating", 36, "正在推演世界线...")

            _run_worldline_simulations(session, task, task_id)

            _update_task(session, task, "simulating", 85, "推演完成")
            publish_progress(task_id, "simulating", 85, "推演完成")

            # === Phase 5: Scoring + reporting ===
            _update_task(session, task, "scoring", 86, "正在评分...")
            publish_progress(task_id, "scoring", 86, "正在评分...")

            _run_scoring(session, task)

            _update_task(session, task, "reporting", 92, "正在生成报告...")
            publish_progress(task_id, "reporting", 92, "正在生成报告...")

            _run_reporting(session, task)

            # === Done ===
            _update_task(session, task, "completed", 100, "任务完成")
            publish_progress(task_id, "completed", 100, "任务完成")

            logger.info("Pipeline completed for task %s", task_id)

        except Exception as e:
            logger.exception("Pipeline failed for task %s", task_id)
            _update_task(session, task, "failed", task.progress, error=str(e))
            publish_progress(task_id, "failed", task.progress, error=str(e))


def _update_task(session, task, status: str, progress: int, message: str = "", error: str | None = None):
    task.status = status
    task.progress = progress
    task.status_message = message or task.status_message
    if error:
        task.error = error
    session.commit()


def _run_extraction(session, task, base_namespace: str) -> None:
    """Phase 1: Extract entities from seed → base graph_namespace (NOT user group_id)."""
    from memory.embedder import get_embeddings
    from memory.extractor import extract_triplets
    from memory.models import Episode
    from memory.temporal import temporal_upsert

    # Create a synthetic episode scoped to the base namespace
    episode = Episode(
        group_id=base_namespace,
        thread_id=task.id,
        role="system",
        content=task.seed_content,
        source_type="document",
        valid_at=task.created_at,
    )
    session.add(episode)
    session.flush()

    # Goal-directed extraction
    triplets = extract_triplets(
        task.seed_content,
        goal=task.goal or "",
    )
    if not triplets:
        logger.info("No triplets extracted for task %s", task.id)
        return

    facts = [t.fact for t in triplets]
    embeddings = get_embeddings(facts)
    while len(embeddings) < len(triplets):
        embeddings.append(None)

    for triplet, embedding in zip(triplets, embeddings):
        temporal_upsert(
            session=session,
            group_id=base_namespace,      # 用 graph_namespace 隔离，非用户 group_id
            triplet=triplet,
            fact_embedding=embedding,
            episode_id=episode.id,
            valid_at=task.created_at,
            generated_by="extraction",
            confidence=triplet.confidence,
        )

    session.commit()
    logger.info("Extracted %d triplets for task %s → namespace %s", len(triplets), task.id, base_namespace)


def _run_profiling(session, task, base_namespace: str) -> None:
    """Phase 2: Generate SimAgent profiles from graph entities."""
    from simulation.profile_generator import generate_profiles
    generate_profiles(session, task, base_namespace)


def _run_bootstrapping(session, task, base_namespace: str, task_id: str) -> None:
    """Phase 3: Initialize worldlines with differentiated LLM assumptions."""
    from simulation.worldline_bootstrap import bootstrap_worldlines
    bootstrap_worldlines(session, task, base_namespace, task_id)


def _run_worldline_simulations(session, task, task_id: str) -> None:
    """Phase 4: Run simulation for each worldline sequentially (MVP: no chord yet)."""
    from simulation.engine import run_worldline
    from simulation.models import SimWorldline
    from simulation.progress import publish_progress
    from sqlalchemy import select

    worldlines = session.execute(
        select(SimWorldline).where(SimWorldline.task_id == task.id)
    ).scalars().all()

    total = len(worldlines)
    for i, wl in enumerate(worldlines):
        pct = 36 + int(49 * i / max(total, 1))
        publish_progress(task_id, "simulating", pct, f"推演世界线 {i+1}/{total}: {wl.assumption_type}")
        run_worldline(session, task, wl)

    session.commit()


def _run_scoring(session, task) -> None:
    """Phase 5a: Score each worldline."""
    from simulation.scorer import score_worldlines
    score_worldlines(session, task)


def _run_reporting(session, task) -> None:
    """Phase 5b: Generate per-worldline reports + summary report."""
    from simulation.reporter import generate_worldline_reports
    generate_worldline_reports(session, task)


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward compat, unused in new pipeline)
# ---------------------------------------------------------------------------

def _run_simulation(task, task_id: str) -> dict:
    """[Legacy] Phase 2: Run the OASIS simulation."""
    from simulation.engine import build_agent_profiles, run_simulation
    from simulation.progress import publish_progress

    profiles = build_agent_profiles(task.seed_content, task.num_agents)

    def on_round(round_num, total, round_data):
        pct = 25 + int(50 * round_num / total)
        msg = f"仿真进行中: 第 {round_num}/{total} 轮 ({round_data.get('posts', 0)} 条发言)"
        publish_progress(task_id, "simulating", pct, msg)

    return run_simulation(
        seed_content=task.seed_content,
        profiles=profiles,
        num_rounds=task.num_rounds,
        scenario=task.scenario,
        on_round_complete=on_round,
    )
