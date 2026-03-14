"""Request/response schemas for simulation API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class SimTaskCreate(BaseModel):
    group_id: str
    title: str
    seed_content: str
    seed_type: str = "text"

    # 推演目标与场景
    goal: str | None = None
    scene_type: str | None = None         # geopolitics | finance | supply_chain | public_opinion | business
    scene_config: dict | None = None

    # 时间参数
    sim_start_time: datetime | None = None
    sim_end_time: datetime | None = None
    time_step_unit: str = "day"           # hour | day | week | month

    # 世界线参数
    num_timelines: int = Field(default=3, ge=1, le=10)

    # 遗留参数（兼容旧接口）
    num_agents: int = Field(default=10, ge=2, le=200)
    num_rounds: int = Field(default=10, ge=1, le=100)
    scenario: str = "social_media"


class SimTaskResponse(BaseModel):
    id: uuid.UUID
    group_id: str
    title: str
    seed_content: str
    seed_type: str
    goal: str | None = None
    scene_type: str | None = None
    num_timelines: int
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


# ---------------------------------------------------------------------------
# Worldline
# ---------------------------------------------------------------------------

class SimWorldlineResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    graph_namespace: str
    initial_assumption: str | None = None
    assumption_type: str
    status: str
    score: float | None = None
    score_detail: dict | None = None
    verdict: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class SimWorldlineEventResponse(BaseModel):
    id: uuid.UUID
    worldline_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    sim_time: datetime | None = None
    step_index: int
    action_type: str | None = None
    description: str | None = None
    impact_score: float
    new_facts: list | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SimAgentResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    entity_id: uuid.UUID | None = None
    name: str
    role: str | None = None
    background: str | None = None
    personality: str | None = None
    ideology: str | None = None
    influence_weight: float
    risk_tolerance: float
    change_resistance: float
    scene_metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class SimReportResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    worldline_id: uuid.UUID | None = None
    title: str
    content: str
    report_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Graph (for /memory/graph)
# ---------------------------------------------------------------------------

class GraphNodeResponse(BaseModel):
    id: str
    name: str
    entity_type: str
    display_name: str | None = None
    group_id: str


class GraphEdgeResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    predicate: str
    fact: str
    generated_by: str | None = None
    confidence: float | None = None
    valid_at: datetime
    expired_at: datetime | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    total_nodes: int
    total_edges: int
