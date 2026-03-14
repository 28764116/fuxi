import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, Float, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def group_id(self) -> str:
        """group_id is the project UUID string — used as the namespace for all entities/edges."""
        return str(self.id)


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="message")  # message | text | json | document
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Entity(Base):
    """DEPRECATED: Entity data has been migrated to Neo4j.

    This model is kept for backwards compatibility and migration scripts only.
    New code should use Neo4jGraphService instead.
    """
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # person | org | location | concept | ...
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_embedding = mapped_column(Vector(1536), nullable=True)

    # --- MVP 新增字段 ---
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)   # 前端展示名（可与 name 不同）
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )  # 扩展属性（国家、行业、规模等）

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    out_edges: Mapped[list["EntityEdge"]] = relationship(
        back_populates="source_entity", foreign_keys="EntityEdge.source_entity_id"
    )
    in_edges: Mapped[list["EntityEdge"]] = relationship(
        back_populates="target_entity", foreign_keys="EntityEdge.target_entity_id"
    )


class EntityEdge(Base):
    """DEPRECATED: Entity relationship data has been migrated to Neo4j.

    This model is kept for backwards compatibility and migration scripts only.
    New code should use Neo4jGraphService instead.
    """
    __tablename__ = "entity_edges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String, nullable=False)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    fact_embedding = mapped_column(Vector(1536), nullable=True)

    # Temporal fields
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Provenance: which episodes contributed to this edge
    episode_ids = mapped_column(ARRAY(Uuid), nullable=False, default=list)

    # --- MVP 新增字段 ---
    generated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # 来源标记: extraction | agent_action | bootstrap
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 置信度 0-1，extraction 时由 LLM 赋值

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source_entity: Mapped["Entity"] = relationship(
        back_populates="out_edges", foreign_keys=[source_entity_id]
    )
    target_entity: Mapped["Entity"] = relationship(
        back_populates="in_edges", foreign_keys=[target_entity_id]
    )

    __table_args__ = (
        # Active facts (most frequent query)
        Index(
            "idx_edges_active",
            "group_id", "source_entity_id",
            postgresql_where=(expired_at.is_(None)),
        ),
        # Temporal range queries
        Index("idx_edges_temporal", "group_id", "valid_at", "expired_at"),
        # Unique constraint: prevent duplicate active edges
        # Same (source, target, predicate) + active (expired_at IS NULL)
        Index(
            "uq_active_edges",
            "group_id", "source_entity_id", "target_entity_id", "predicate",
            unique=True,
            postgresql_where=(expired_at.is_(None)),
        ),
    )
