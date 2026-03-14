import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EpisodeCreate(BaseModel):
    group_id: str
    thread_id: uuid.UUID
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str
    source_type: str = "message"
    valid_at: datetime


class EpisodeResponse(BaseModel):
    id: uuid.UUID
    group_id: str
    thread_id: uuid.UUID
    role: str
    content: str
    source_type: str
    valid_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextResponse(BaseModel):
    thread_id: uuid.UUID
    episodes: list[EpisodeResponse]
    context: str


class EntityResponse(BaseModel):
    id: uuid.UUID
    group_id: str
    name: str
    entity_type: str
    display_name: str | None = None  # 原始名称，用于前端展示
    summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EntityEdgeResponse(BaseModel):
    id: uuid.UUID
    group_id: str
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    predicate: str
    fact: str
    valid_at: datetime
    expired_at: datetime | None = None
    episode_ids: list[uuid.UUID] = []
    created_at: datetime
    score: float | None = None

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    query: str
    results: list[EntityEdgeResponse]
