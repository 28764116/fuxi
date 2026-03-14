"""Simulation task and report data models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SimTask(Base):
    """A simulation task representing the full lifecycle.

    Status flow:
        pending → extracting → profiling → bootstrapping → simulating → scoring → reporting → completed
                                                                                               └→ failed (from any state)
        Any state → paused (pause/resume, MVP 暂不实现)
    """

    __tablename__ = "sim_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # User input
    title: Mapped[str] = mapped_column(String, nullable=False)
    seed_content: Mapped[str] = mapped_column(Text, nullable=False)  # raw seed material
    seed_type: Mapped[str] = mapped_column(String, default="text")  # text | document

    # --- 推演目标与场景（MVP 扩展字段）---
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)  # 推演目标，如"评估贸易战对半导体供应链的影响"
    scene_type: Mapped[str | None] = mapped_column(String, nullable=True)  # geopolitics | finance | ...
    scene_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 场景额外参数覆盖

    # --- 时间参数 ---
    sim_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sim_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_step_unit: Mapped[str] = mapped_column(String, default="day")  # hour | day | week | month

    # --- 世界线参数 ---
    num_timelines: Mapped[int] = mapped_column(Integer, default=3)  # 生成几条世界线

    # --- 遗留 OASIS 参数（后续迁移，MVP 保留兼容）---
    num_agents: Mapped[int] = mapped_column(Integer, default=10)
    num_rounds: Mapped[int] = mapped_column(Integer, default=10)
    scenario: Mapped[str] = mapped_column(String, default="social_media")

    # Status tracking
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    # 合法状态: pending | extracting | profiling | bootstrapping | simulating | scoring | reporting | completed | failed | paused
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results
    sim_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # raw OASIS output（遗留）

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reports: Mapped[list["SimReport"]] = relationship(back_populates="task")
    agents: Mapped[list["SimAgent"]] = relationship(back_populates="task")
    worldlines: Mapped[list["SimWorldline"]] = relationship(back_populates="task")


class SimReport(Base):
    """Generated report from a simulation task."""

    __tablename__ = "sim_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sim_tasks.id"), nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown report
    report_type: Mapped[str] = mapped_column(String, default="summary")  # summary | worldline | comparison

    # 关联世界线（worldline 报告时填写，总报告为 NULL）
    worldline_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sim_worldlines.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["SimTask"] = relationship(back_populates="reports")
    worldline: Mapped["SimWorldline | None"] = relationship(back_populates="reports")


class SimAgent(Base):
    """Agent profile for a simulation task (三层画像).

    三层结构：
      - 静态层：name, role, background, personality, ideology
      - 动态参数层：influence_weight, risk_tolerance, change_resistance
      - 场景元数据层：scene_metadata（含 information_access 等场景相关字段）
    """

    __tablename__ = "sim_agents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sim_tasks.id"), nullable=False, index=True)

    # 绑定知识图谱节点
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entities.id"), nullable=True
    )

    # --- 静态层 ---
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String, nullable=True)        # 职位/角色
    background: Mapped[str | None] = mapped_column(Text, nullable=True)    # 背景信息
    personality: Mapped[str | None] = mapped_column(String, nullable=True) # 性格特征
    ideology: Mapped[str | None] = mapped_column(String, nullable=True)    # 立场/意识形态

    # --- 动态参数层 ---
    influence_weight: Mapped[float] = mapped_column(Float, default=0.5)    # 影响力权重 0-1
    risk_tolerance: Mapped[float] = mapped_column(Float, default=0.5)      # 风险容忍度 0-1
    change_resistance: Mapped[float] = mapped_column(Float, default=0.5)   # 变化抵抗力 0-1

    # --- 场景元数据层 ---
    scene_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 示例：{"information_access": "full|partial|limited", "resources": {...}, ...}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["SimTask"] = relationship(back_populates="agents")
    checkpoints: Mapped[list["SimCheckpoint"]] = relationship(back_populates="agent")


class SimWorldline(Base):
    """A single timeline/worldline in a multi-world simulation.

    每条世界线有独立的 graph_namespace，克隆自基础图谱。
    verdict: above_water（正面/可控）| below_water（负面/失控）| neutral
    """

    __tablename__ = "sim_worldlines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sim_tasks.id"), nullable=False, index=True)

    # 图谱命名空间（形如 task_{task_id}_wl_{n}）
    graph_namespace: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # 世界线初始假设（由 LLM bootstrap 生成）
    initial_assumption: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumption_type: Mapped[str] = mapped_column(String, default="neutral")  # optimistic | neutral | pessimistic

    # 推演状态
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    # 合法状态: pending | running | completed | failed

    # 评分（scorer 阶段填写）
    score: Mapped[float | None] = mapped_column(Float, nullable=True)          # 0-100
    score_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)    # 各维度明细
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)         # above_water | below_water | neutral

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task: Mapped["SimTask"] = relationship(back_populates="worldlines")
    events: Mapped[list["SimWorldlineEvent"]] = relationship(back_populates="worldline")
    checkpoints: Mapped[list["SimCheckpoint"]] = relationship(back_populates="worldline")
    reports: Mapped[list["SimReport"]] = relationship(back_populates="worldline")


class SimWorldlineEvent(Base):
    """Event stream for a worldline (用于前端时间轴渲染).

    每个 Agent 执行一步产生一条事件记录。
    """

    __tablename__ = "sim_worldline_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    worldline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sim_worldlines.id"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sim_agents.id"), nullable=True
    )

    # 仿真时间（非 wall clock，是推演内的时间）
    sim_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 第几步

    # 事件内容
    action_type: Mapped[str | None] = mapped_column(String, nullable=True)  # 由 scene_registry 定义
    description: Mapped[str | None] = mapped_column(Text, nullable=True)    # 人类可读描述
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)         # 0-1，影响力评分

    # 产生的新事实（写回图谱的三元组摘要）
    new_facts: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    worldline: Mapped["SimWorldline"] = relationship(back_populates="events")


class SimCheckpoint(Base):
    """Agent dynamic state snapshot at each step.

    存储 Agent 在某一推演步骤结束时的动态状态，以及待响应事件队列。
    MVP 阶段写入但不实现 resume 逻辑。
    """

    __tablename__ = "sim_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    worldline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sim_worldlines.id"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sim_agents.id"), nullable=False, index=True
    )

    step_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Agent 当前动态状态（情绪、立场变化等）
    dynamic_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 待响应事件队列（高影响力事件推入，下一步优先响应）
    pending_reactions: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    worldline: Mapped["SimWorldline"] = relationship(back_populates="checkpoints")
    agent: Mapped["SimAgent"] = relationship(back_populates="checkpoints")
