"""Simulation task and report data models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SimTask(Base):
    """A simulation task representing the full lifecycle.

    Status flow: pending → extracting → simulating → reporting → completed
                                                                 └→ failed (from any state)
    """

    __tablename__ = "sim_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # User input
    title: Mapped[str] = mapped_column(String, nullable=False)
    seed_content: Mapped[str] = mapped_column(Text, nullable=False)  # raw seed material
    seed_type: Mapped[str] = mapped_column(String, default="text")  # text | document

    # Simulation parameters
    num_agents: Mapped[int] = mapped_column(Integer, default=50)
    num_rounds: Mapped[int] = mapped_column(Integer, default=10)
    scenario: Mapped[str] = mapped_column(String, default="social_media")  # social_media | forum | custom

    # Status tracking
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results
    sim_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # raw OASIS output

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reports: Mapped[list["SimReport"]] = relationship(back_populates="task")


class SimReport(Base):
    """Generated report from a simulation task."""

    __tablename__ = "sim_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sim_tasks.id"), nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown report
    report_type: Mapped[str] = mapped_column(String, default="summary")  # summary | detailed | custom

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["SimTask"] = relationship(back_populates="reports")
