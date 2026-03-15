import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import json

logger = logging.getLogger(__name__)

from app.auth import require_api_key
from app.database import get_session
from memory.models import Entity, EntityEdge, Episode, Project
from memory.schemas import (
    ContextResponse,
    EntityEdgeResponse,
    EntityResponse,
    EpisodeCreate,
    EpisodeResponse,
    SearchResponse,
)
from memory.service import (
    get_context,
    get_entity_facts,
    get_entity_facts_at,
    ingest_episode,
    search_edges,
    search_entities,
)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_api_key)])
ws_router = APIRouter(prefix="/memory", tags=["memory-ws"])  # WebSocket router without auth dependency


# ---- Projects ----

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None

class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    group_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(session: AsyncSession = Depends(get_session)):
    stmt = select(Project).order_by(Project.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, session: AsyncSession = Depends(get_session)):
    project = Project(name=data.name, description=data.description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    group_id = str(project_id)
    # Cascade delete all project data
    await session.execute(
        select(EntityEdge).where(EntityEdge.group_id == group_id)
    )
    for table_model in [EntityEdge, Entity, Episode]:
        stmt = select(table_model).where(table_model.group_id == group_id)
        rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            await session.delete(row)
    await session.delete(project)
    await session.commit()


# ---- Episodes ----


@router.post("/episodes", response_model=EpisodeResponse, status_code=201)
async def create_episode(
    data: EpisodeCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # 读取用户语言偏好
    language = request.headers.get("X-User-Language", "zh")
    episode = await ingest_episode(session, data, language=language)
    return episode


@router.get("/context/{thread_id}", response_model=ContextResponse)
async def read_context(
    thread_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    episodes, context = await get_context(session, thread_id, limit)
    return ContextResponse(
        thread_id=thread_id,
        episodes=episodes,
        context=context,
    )


# ---- Search ----


@router.get("/search", response_model=SearchResponse)
async def search_facts(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    group_id: str = Query(..., description="分组 ID"),
    limit: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """TODO: Migrate to Neo4j vector search. Currently queries PostgreSQL (may return empty results)."""
    edges_with_scores = await search_edges(session, q, group_id, limit)
    results = [
        EntityEdgeResponse(
            id=edge.id,
            group_id=edge.group_id,
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            predicate=edge.predicate,
            fact=edge.fact,
            valid_at=edge.valid_at,
            expired_at=edge.expired_at,
            episode_ids=edge.episode_ids or [],
            created_at=edge.created_at,
            score=score,
        )
        for edge, score in edges_with_scores
    ]
    return SearchResponse(query=q, results=results)


@router.get("/search/entities", response_model=list[EntityResponse])
async def search_entity_list(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    group_id: str = Query(..., description="分组 ID"),
    limit: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """TODO: Migrate to Neo4j vector search. Currently queries PostgreSQL (may return empty results)."""
    entities_with_scores = await search_entities(session, q, group_id, limit)
    return [entity for entity, _score in entities_with_scores]


# ---- Entities ----


@router.get("/entities")
async def list_entities(
    group_id: str = Query(..., description="分组 ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Get entities from Neo4j"""
    from memory.neo4j_service import Neo4jGraphService

    neo4j_service = Neo4jGraphService()
    try:
        entities = neo4j_service.get_all_entities(group_id)
        # Apply offset/limit
        return entities[offset:offset+limit]
    finally:
        neo4j_service.close()


# DEPRECATED: This endpoint queries PostgreSQL Entity table
# Entity data has been migrated to Neo4j. Use /entities with group_id filter instead.
# @router.get("/entities/{entity_id}", response_model=EntityResponse)
# async def get_entity(entity_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
#     entity = await session.get(Entity, entity_id)
#     if not entity:
#         raise HTTPException(status_code=404, detail="Entity not found")
#     return entity


@router.get("/edges")
async def list_edges(
    group_id: str = Query(..., description="分组 ID"),
    active_only: bool = Query(default=True, description="只返回活跃边（expired_at IS NULL）"),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """Get all edges from Neo4j"""
    from memory.neo4j_service import Neo4jGraphService

    neo4j_service = Neo4jGraphService()
    try:
        edges = neo4j_service.get_all_edges(group_id, active_only=active_only)
        # Apply offset/limit
        return edges[offset:offset+limit]
    finally:
        neo4j_service.close()


# DEPRECATED: This endpoint queries PostgreSQL EntityEdge table
# Relationship data has been migrated to Neo4j. Use /edges with group_id filter instead.
# @router.get("/entities/{entity_id}/edges", response_model=list[EntityEdgeResponse])
# async def get_entity_edges(entity_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
#     stmt = (
#         select(EntityEdge)
#         .where((EntityEdge.source_entity_id == entity_id) | (EntityEdge.target_entity_id == entity_id))
#         .order_by(EntityEdge.created_at.desc())
#     )
#     result = await session.execute(stmt)
#     return list(result.scalars().all())


# ---- Facts (Temporal) ----


# DEPRECATED: This endpoint queries PostgreSQL
# Entity relationship data has been migrated to Neo4j. Use /edges with filtering instead.
# @router.get("/facts/{entity_id}", response_model=list[EntityEdgeResponse])
# async def get_facts(
#     entity_id: uuid.UUID,
#     include_expired: bool = Query(default=False, description="是否包含已过期事实"),
#     session: AsyncSession = Depends(get_session),
# ):
#     """Get all facts for an entity. By default only returns active (non-expired) facts."""
#     entity = await session.get(Entity, entity_id)
#     if not entity:
#         raise HTTPException(status_code=404, detail="Entity not found")
#     edges = await get_entity_facts(session, entity_id, active_only=not include_expired)
#     return edges


# DEPRECATED: This endpoint queries PostgreSQL
# Entity relationship data has been migrated to Neo4j. Temporal queries need to be implemented in Neo4j.
# @router.get("/facts/{entity_id}/at", response_model=list[EntityEdgeResponse])
# async def get_facts_at_time(
#     entity_id: uuid.UUID,
#     t: datetime = Query(..., description="查询时间点 (ISO 8601)"),
#     session: AsyncSession = Depends(get_session),
# ):
#     """Time-travel query: get facts that were valid at a specific point in time."""
#     entity = await session.get(Entity, entity_id)
#     if not entity:
#         raise HTTPException(status_code=404, detail="Entity not found")
#     edges = await get_entity_facts_at(session, entity_id, t)
#     return edges


# ---- Episodes list ----


@router.get("/episodes", response_model=list[EpisodeResponse])
async def list_episodes(
    thread_id: uuid.UUID = Query(..., description="会话 ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Episode)
        .where(Episode.thread_id == thread_id)
        .order_by(Episode.valid_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---- File Upload ----


class DocumentUploadResponse(BaseModel):
    task_id: str
    message: str
    file_name: str
    file_size: int

class DocumentTaskStatus(BaseModel):
    task_id: str
    state: str  # PENDING, PROGRESS, SUCCESS, FAILURE
    stage: str | None = None
    progress: int = 0
    current: int = 0
    total: int = 0
    result: dict | None = None
    error: str | None = None


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_file(
    group_id: str = Form(...),
    thread_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
):
    """Upload a document file and process asynchronously with real-time progress.

    返回 task_id，前端可以通过 WebSocket /memory/ws/upload/{task_id} 接收实时进度
    """
    from memory.file_parser import parse_file
    from worker import celery_app

    # 读取用户语言偏好
    language = request.headers.get("X-User-Language", "zh") if request else "zh"
    logger.info(f"User language preference: {language}")

    # 验证文件类型
    suffix = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    allowed_types = {".pdf", ".txt", ".md", ".csv", ".log", ".json", ".xml", ".html"}
    if suffix not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}。支持的类型: {', '.join(allowed_types)}"
        )

    # 保存临时文件
    import os
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}{suffix}")

    content = await file.read()
    with open(tmp_path, 'wb') as f:
        f.write(content)

    file_size = len(content)
    logger.info(f"Saved document {file.filename} to {tmp_path}: {file_size} bytes")

    # 启动异步任务（传递语言参数）
    task = celery_app.send_task(
        "memory.process_document",
        args=[group_id, str(thread_id), tmp_path, file.filename, language]
    )

    return DocumentUploadResponse(
        task_id=task.id,
        message=f"文档上传成功，正在处理",
        file_name=file.filename,
        file_size=file_size,
    )


@router.get("/upload/status/{task_id}", response_model=DocumentTaskStatus)
async def get_upload_status(task_id: str):
    """获取文档处理任务状态 (参考 MiroFish TaskManager)."""
    from worker import celery_app
    from celery.result import AsyncResult

    task = AsyncResult(task_id, app=celery_app)

    response = DocumentTaskStatus(
        task_id=task_id,
        state=task.state,
    )

    if task.state == 'PENDING':
        response.stage = '⏳ 等待处理'
        response.progress = 0
    elif task.state == 'PROGRESS':
        info = task.info or {}
        response.stage = info.get('stage', '处理中')
        response.progress = info.get('progress', 0)
        response.current = info.get('current', 0)
        response.total = info.get('total', 0)
        # 将 info 作为 result 返回，前端可以访问 entities_count 等
        response.result = info
    elif task.state == 'SUCCESS':
        response.stage = '✅ 完成'
        response.progress = 100
        response.result = task.result
    elif task.state == 'FAILURE':
        response.stage = '❌ 失败'
        response.error = str(task.info)

    return response


@ws_router.websocket("/ws/upload/{task_id}")
async def websocket_upload_progress(
    websocket: WebSocket,
    task_id: str,
):
    """WebSocket endpoint for real-time document processing progress.

    前端连接后，实时推送处理进度：
    - stage: 当前阶段描述
    - progress: 0-100
    - current: 当前处理的 chunk
    - total: 总 chunk 数
    - entities_count: 已提取实体数
    - triplets_count: 已提取关系数
    """
    await websocket.accept()

    from worker import celery_app
    from celery.result import AsyncResult

    try:
        task = AsyncResult(task_id, app=celery_app)
        last_state = None

        while True:
            state = task.state
            info = task.info or {}

            # 只在状态变化时推送
            current_state_str = json.dumps({'state': state, 'info': info}, sort_keys=True)
            if current_state_str != last_state:
                message = {
                    'task_id': task_id,
                    'state': state,
                }

                if state == 'PENDING':
                    message.update({
                        'stage': '⏳ 等待处理',
                        'progress': 0,
                    })
                elif state == 'PROGRESS':
                    message.update({
                        'stage': info.get('stage', '处理中'),
                        'progress': info.get('progress', 0),
                        'current': info.get('current', 0),
                        'total': info.get('total', 0),
                        'entities_count': info.get('entities_count', 0),
                        'triplets_count': info.get('triplets_count', 0),
                    })
                elif state == 'SUCCESS':
                    result = task.result or {}
                    message.update({
                        'stage': '✅ 处理完成',
                        'progress': 100,
                        'entities_count': result.get('entities_count', 0),
                        'triplets_count': result.get('triplets_count', 0),
                        'chunks_processed': result.get('chunks_processed', 0),
                    })
                elif state == 'FAILURE':
                    message.update({
                        'stage': '❌ 处理失败',
                        'error': str(task.info),
                    })

                await websocket.send_json(message)
                last_state = current_state_str

                # 任务完成，关闭连接
                if state in ('SUCCESS', 'FAILURE'):
                    break

            await asyncio.sleep(0.5)  # 每0.5秒检查一次

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for task {task_id}: {e}")
        try:
            await websocket.send_json({
                'task_id': task_id,
                'state': 'ERROR',
                'stage': '❌ 连接错误',
                'error': str(e),
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
