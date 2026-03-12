"""Request/response schemas for simulation API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SimTaskCreate(BaseModel):
    group_id: str
    title: str
    seed_content: str
    seed_type: str = "text"
    num_agents: int = Field(default=50, ge=2, le=1000)
    num_rounds: int = Field(default=10, ge=1, le=100)
    scenario: str = "social_media"


class SimTaskResponse(BaseModel):
    id: uuid.UUID
    group_id: str
    title: str
    seed_content: str
    seed_type: str
    num_agents: int
    num_rounds: int
    scenario: str
    status: str
    progress: int
    status_message: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SimTaskStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    progress: int
    status_message: str | None = None
    error: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SimReportResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    content: str
    report_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
