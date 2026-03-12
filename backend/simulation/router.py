"""Simulation API routes."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_session
from simulation.models import SimReport, SimTask
from simulation.schemas import (
    SimReportResponse,
    SimTaskCreate,
    SimTaskResponse,
    SimTaskStatusResponse,
)

router = APIRouter(prefix="/simulation", tags=["simulation"], dependencies=[Depends(require_api_key)])


# ---- Task CRUD ----


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
        num_agents=data.num_agents,
        num_rounds=data.num_rounds,
        scenario=data.scenario,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # Push to Celery pipeline
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
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/tasks/{task_id}", response_model=SimTaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/status", response_model=SimTaskStatusResponse)
async def get_task_status(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---- Reports ----


@router.get("/tasks/{task_id}/reports", response_model=list[SimReportResponse])
async def get_task_reports(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(SimTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    stmt = (
        select(SimReport)
        .where(SimReport.task_id == task_id)
        .order_by(SimReport.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/reports/{report_id}", response_model=SimReportResponse)
async def get_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    report = await session.get(SimReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ---- WebSocket for real-time progress ----


@router.websocket("/ws/{task_id}")
async def ws_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task progress updates.

    Client connects, receives JSON progress messages until task completes or fails.
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
            message = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                timeout=60,
            )
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)

                if data.get("status") in ("completed", "failed"):
                    break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await r.close()
