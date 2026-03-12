import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_session
from memory.models import Entity, EntityEdge, Episode
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


# ---- Episodes ----


@router.post("/episodes", response_model=EpisodeResponse, status_code=201)
async def create_episode(
    data: EpisodeCreate,
    session: AsyncSession = Depends(get_session),
):
    episode = await ingest_episode(session, data)
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
    entities_with_scores = await search_entities(session, q, group_id, limit)
    return [entity for entity, _score in entities_with_scores]


# ---- Entities ----


@router.get("/entities", response_model=list[EntityResponse])
async def list_entities(
    group_id: str = Query(..., description="分组 ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Entity)
        .where(Entity.group_id == group_id)
        .order_by(Entity.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    entity = await session.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/entities/{entity_id}/edges", response_model=list[EntityEdgeResponse])
async def get_entity_edges(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(EntityEdge)
        .where(
            (EntityEdge.source_entity_id == entity_id)
            | (EntityEdge.target_entity_id == entity_id)
        )
        .order_by(EntityEdge.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---- Facts (Temporal) ----


@router.get("/facts/{entity_id}", response_model=list[EntityEdgeResponse])
async def get_facts(
    entity_id: uuid.UUID,
    include_expired: bool = Query(default=False, description="是否包含已过期事实"),
    session: AsyncSession = Depends(get_session),
):
    """Get all facts for an entity. By default only returns active (non-expired) facts."""
    entity = await session.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    edges = await get_entity_facts(session, entity_id, active_only=not include_expired)
    return edges


@router.get("/facts/{entity_id}/at", response_model=list[EntityEdgeResponse])
async def get_facts_at_time(
    entity_id: uuid.UUID,
    t: datetime = Query(..., description="查询时间点 (ISO 8601)"),
    session: AsyncSession = Depends(get_session),
):
    """Time-travel query: get facts that were valid at a specific point in time."""
    entity = await session.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    edges = await get_entity_facts_at(session, entity_id, t)
    return edges


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


@router.post("/upload", response_model=list[EpisodeResponse], status_code=201)
async def upload_file(
    group_id: str = Form(...),
    thread_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a document file, parse it into chunks, and ingest as episodes."""
    from memory.file_parser import chunk_text, parse_file

    suffix = "." + file.filename.rsplit(".", 1)[-1] if "." in file.filename else ""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()

        try:
            text = parse_file(tmp.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    chunks = chunk_text(text)
    episodes = []
    now = datetime.now(timezone.utc)
    for chunk in chunks:
        data = EpisodeCreate(
            group_id=group_id,
            thread_id=thread_id,
            role="system",
            content=chunk,
            source_type="document",
            valid_at=now,
        )
        episode = await ingest_episode(session, data)
        episodes.append(episode)

    return episodes
