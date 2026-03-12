"""Celery tasks for the simulation pipeline.

Pipeline: pending → extracting → simulating → reporting → completed
"""

import logging
import uuid

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="simulation.run_pipeline")
def run_pipeline(task_id: str) -> None:
    """Execute the full simulation pipeline for a task.

    Steps:
      1. extracting  — Extract entities from seed material into knowledge graph
      2. simulating  — Run OASIS social media simulation
      3. reporting   — Generate analysis report from results
      4. completed   — Done
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
            # === Phase 1: Entity extraction ===
            _update_task(session, task, "extracting", 5, "正在从种子材料中提取实体关系...")
            publish_progress(task_id, "extracting", 5, "正在提取实体关系...")

            _run_extraction(session, task)

            _update_task(session, task, "extracting", 20, "实体关系提取完成")
            publish_progress(task_id, "extracting", 20, "实体关系提取完成")

            # === Phase 2: Simulation ===
            _update_task(session, task, "simulating", 25, "正在生成 Agent 角色...")
            publish_progress(task_id, "simulating", 25, "正在生成 Agent 角色...")

            sim_result = _run_simulation(task, task_id)

            task.sim_result = sim_result
            _update_task(session, task, "simulating", 75, "仿真完成")
            publish_progress(task_id, "simulating", 75, "仿真完成")

            # === Phase 3: Report generation ===
            _update_task(session, task, "reporting", 80, "正在生成分析报告...")
            publish_progress(task_id, "reporting", 80, "正在生成分析报告...")

            report_content = _run_reporting(task)

            report = SimReport(
                task_id=task.id,
                title=f"{task.title} - 仿真分析报告",
                content=report_content,
                report_type="summary",
            )
            session.add(report)

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


def _run_extraction(session, task):
    """Phase 1: Extract entities from seed content into knowledge graph."""
    from memory.extractor import extract_triplets
    from memory.embedder import get_embeddings
    from memory.temporal import temporal_upsert
    from memory.models import Episode

    # Create an episode from the seed content
    episode = Episode(
        group_id=task.group_id,
        thread_id=task.id,  # use task_id as thread_id
        role="system",
        content=task.seed_content,
        source_type="document",
        valid_at=task.created_at,
    )
    session.add(episode)
    session.flush()

    # Extract triplets
    triplets = extract_triplets(task.seed_content)
    if not triplets:
        logger.info("No triplets extracted from seed content of task %s", task.id)
        return

    # Generate embeddings and upsert
    facts = [t.fact for t in triplets]
    embeddings = get_embeddings(facts)
    while len(embeddings) < len(triplets):
        embeddings.append(None)

    for triplet, embedding in zip(triplets, embeddings):
        temporal_upsert(
            session=session,
            group_id=task.group_id,
            triplet=triplet,
            fact_embedding=embedding,
            episode_id=episode.id,
            valid_at=task.created_at,
        )

    session.commit()
    logger.info("Extracted %d triplets from task %s seed", len(triplets), task.id)


def _run_simulation(task, task_id: str) -> dict:
    """Phase 2: Run the OASIS simulation."""
    from simulation.engine import build_agent_profiles, run_simulation
    from simulation.progress import publish_progress

    # Generate agent profiles
    profiles = build_agent_profiles(task.seed_content, task.num_agents)

    # Run simulation with progress callback
    def on_round(round_num, total, round_data):
        pct = 25 + int(50 * round_num / total)  # 25-75%
        msg = f"仿真进行中: 第 {round_num}/{total} 轮 ({round_data.get('posts', 0)} 条发言)"
        publish_progress(task_id, "simulating", pct, msg)

    result = run_simulation(
        seed_content=task.seed_content,
        profiles=profiles,
        num_rounds=task.num_rounds,
        scenario=task.scenario,
        on_round_complete=on_round,
    )
    return result


def _run_reporting(task) -> str:
    """Phase 3: Generate analysis report."""
    from simulation.reporter import generate_report

    return generate_report(task.title, task.sim_result)
