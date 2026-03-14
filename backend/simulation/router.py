"""Simulation API routes."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_session
from simulation.models import SimAgent, SimReport, SimTask, SimWorldline, SimWorldlineEvent
from simulation.schemas import (
    GraphResponse,
    SimAgentResponse,
    SimReportResponse,
    SimTaskCreate,
    SimTaskResponse,
    SimTaskStatusResponse,
    SimWorldlineEventResponse,
    SimWorldlineResponse,
)

router = APIRouter(
    prefix="/simulation",
    tags=["simulation"],
    dependencies=[Depends(require_api_key)],
)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post("/tasks", response_model=SimTaskResponse, status_code=201)
async def create_task(
    data: SimTaskCreate,
    session: AsyncSession = Depends(get_session),
):
    """Submit a new simulation task. Processing starts asynchronously."""
    task = SimTask(
        group_id=data.group_id,
        title=data.title,
        seed_content=data.seed_content,
        seed_type=data.seed_type,
        goal=data.goal,
        scene_type=data.scene_type,
        scene_config=data.scene_config,
        sim_start_time=data.sim_start_time,
        sim_end_time=data.sim_end_time,
        time_step_unit=data.time_step_unit,
        num_timelines=data.num_timelines,
        num_agents=data.num_agents,
        num_rounds=data.num_rounds,
        scenario=data.scenario,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from worker import celery_app
    celery_app.send_task("simulation.run_pipeline", args=[str(task.id)])

    return task


@router.get("/tasks", response_model=list[SimTaskResponse])
async def list_tasks(
    group_id: str = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(SimTask)
        .where(SimTask.group_id == group_id)
        .order_by(SimTask.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/tasks/{task_id}", response_model=SimTaskResponse)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/status", response_model=SimTaskStatusResponse)
async def get_task_status(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/agents", response_model=list[SimAgentResponse])
async def get_task_agents(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """List all agents generated for a task."""
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    stmt = (
        select(SimAgent)
        .where(SimAgent.task_id == task_id)
        .order_by(SimAgent.influence_weight.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Worldlines
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/worldlines", response_model=list[SimWorldlineResponse])
async def get_task_worldlines(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """List all worldlines for a task (with scores)."""
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    stmt = (
        select(SimWorldline)
        .where(SimWorldline.task_id == task_id)
        .order_by(SimWorldline.score.desc().nulls_last())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/worldlines/{worldline_id}/events", response_model=list[SimWorldlineEventResponse])
async def get_worldline_events(
    worldline_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Get event stream for a worldline (time axis data)."""
    wl = await session.get(SimWorldline, worldline_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Worldline not found")

    stmt = (
        select(SimWorldlineEvent)
        .where(SimWorldlineEvent.worldline_id == worldline_id)
        .order_by(SimWorldlineEvent.step_index.asc(), SimWorldlineEvent.created_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/worldlines/{worldline_id}/snapshot", response_model=GraphResponse)
async def get_worldline_snapshot(
    worldline_id: uuid.UUID,
    t: str | None = Query(default=None, description="ISO datetime — facts valid at this time"),
    session: AsyncSession = Depends(get_session),
):
    """Get graph snapshot for a worldline at an optional point in time."""
    from datetime import datetime as dt
    from memory.models import Entity, EntityEdge
    from sqlalchemy import and_

    wl = await session.get(SimWorldline, worldline_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Worldline not found")

    ns = wl.graph_namespace

    # Parse optional time filter
    filter_time: dt | None = None
    if t:
        try:
            filter_time = dt.fromisoformat(t)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format for 't'")

    # Fetch entities
    entities = list(
        (await session.execute(select(Entity).where(Entity.group_id == ns))).scalars().all()
    )

    # Fetch edges
    edge_stmt = select(EntityEdge).where(EntityEdge.group_id == ns)
    if filter_time:
        edge_stmt = edge_stmt.where(
            and_(
                EntityEdge.valid_at <= filter_time,
                (EntityEdge.expired_at.is_(None)) | (EntityEdge.expired_at > filter_time),
            )
        )
    else:
        edge_stmt = edge_stmt.where(EntityEdge.expired_at.is_(None))

    edges = list((await session.execute(edge_stmt)).scalars().all())

    from simulation.schemas import GraphEdgeResponse, GraphNodeResponse
    nodes_out = [
        GraphNodeResponse(
            id=str(e.id), name=e.name, entity_type=e.entity_type,
            display_name=e.display_name, group_id=e.group_id,
        )
        for e in entities
    ]
    edges_out = [
        GraphEdgeResponse(
            id=str(e.id), source_id=str(e.source_entity_id),
            target_id=str(e.target_entity_id), predicate=e.predicate,
            fact=e.fact, generated_by=e.generated_by, confidence=e.confidence,
            valid_at=e.valid_at, expired_at=e.expired_at,
        )
        for e in edges
    ]
    return GraphResponse(
        nodes=nodes_out, edges=edges_out,
        total_nodes=len(nodes_out), total_edges=len(edges_out),
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/reports", response_model=list[SimReportResponse])
async def get_task_reports(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    stmt = (
        select(SimReport)
        .where(SimReport.task_id == task_id)
        .order_by(SimReport.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/reports/{report_id}", response_model=SimReportResponse)
async def get_report(report_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    report = await session.get(SimReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ---------------------------------------------------------------------------
# Memory graph (全量图谱, 供前端渲染)
# ---------------------------------------------------------------------------

@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    group_id: str = Query(..., description="graph_namespace 或用户 group_id"),
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
):
    """Return all nodes and edges for a given group_id/namespace."""
    from memory.models import Entity, EntityEdge

    entities = list(
        (await session.execute(
            select(Entity).where(Entity.group_id == group_id)
        )).scalars().all()
    )

    edge_stmt = select(EntityEdge).where(EntityEdge.group_id == group_id)
    if active_only:
        edge_stmt = edge_stmt.where(EntityEdge.expired_at.is_(None))
    edges = list((await session.execute(edge_stmt)).scalars().all())

    from simulation.schemas import GraphEdgeResponse, GraphNodeResponse
    nodes_out = [
        GraphNodeResponse(
            id=str(e.id), name=e.name, entity_type=e.entity_type,
            display_name=e.display_name, group_id=e.group_id,
        )
        for e in entities
    ]
    edges_out = [
        GraphEdgeResponse(
            id=str(e.id), source_id=str(e.source_entity_id),
            target_id=str(e.target_entity_id), predicate=e.predicate,
            fact=e.fact, generated_by=e.generated_by, confidence=e.confidence,
            valid_at=e.valid_at, expired_at=e.expired_at,
        )
        for e in edges
    ]
    return GraphResponse(
        nodes=nodes_out, edges=edges_out,
        total_nodes=len(nodes_out), total_edges=len(edges_out),
    )


# ---------------------------------------------------------------------------
# Scene registry
# ---------------------------------------------------------------------------

@router.get("/scenes")
async def list_scenes():
    """List all available scene types."""
    from simulation.scene_registry import list_scenes as _list
    return _list()


# ---------------------------------------------------------------------------
# WebSocket: real-time progress
# ---------------------------------------------------------------------------

@router.websocket("/ws/{task_id}")
async def ws_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task progress updates.

    Messages:
      {"status": "extracting", "progress": 5, "message": "...", "worldline_id": null, "latest_event": null}
      ...
      {"status": "completed", "progress": 100, "message": "任务完成"}
      {"status": "failed",    "progress": X,   "error": "..."}
    """
    await websocket.accept()

    import redis.asyncio as aioredis
    from app.config import settings

    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    channel = f"sim:progress:{task_id}"

    try:
        await pubsub.subscribe(channel)

        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
                continue

            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
                if data.get("status") in ("completed", "failed"):
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await r.close()
