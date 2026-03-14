"""Reindex embeddings for all existing entities and edges.

Usage:
    cd backend
    python scripts/reindex_embeddings.py [--group GROUP_ID] [--batch-size 64] [--dry-run]

Options:
    --group     Only reindex a specific group_id (default: all groups)
    --batch-size Embedding batch size (default: 64)
    --dry-run   Show counts only, no writes
    --missing-only  Only fill NULL embeddings (skip if already has one)
"""

import argparse
import logging
import sys
from pathlib import Path

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def reindex(group_id: str | None, batch_size: int, dry_run: bool, missing_only: bool):
    from app.database import sync_session_factory
    from memory.embedder import get_embeddings
    from memory.models import Entity, EntityEdge
    from sqlalchemy import select

    with sync_session_factory() as session:
        # ── 1. Entity summary embeddings ──────────────────────────────
        stmt = select(Entity).where(Entity.summary.isnot(None))
        if group_id:
            stmt = stmt.where(Entity.group_id == group_id)
        if missing_only:
            stmt = stmt.where(Entity.summary_embedding.is_(None))

        entities = list(session.execute(stmt).scalars().all())
        logger.info("Entities to reindex: %d", len(entities))

        if not dry_run:
            for i in range(0, len(entities), batch_size):
                batch = entities[i : i + batch_size]
                texts = [e.summary for e in batch]
                embeddings = get_embeddings(texts, embedding_type="db")
                if len(embeddings) != len(batch):
                    logger.warning(
                        "Batch %d: expected %d embeddings, got %d — skipping",
                        i // batch_size,
                        len(batch),
                        len(embeddings),
                    )
                    continue
                for entity, emb in zip(batch, embeddings):
                    entity.summary_embedding = emb
                session.flush()
                logger.info("Entity batch %d/%d done", i // batch_size + 1, (len(entities) + batch_size - 1) // batch_size)

            session.commit()
            logger.info("Entity embeddings committed.")

        # ── 2. Edge fact embeddings ────────────────────────────────────
        stmt = select(EntityEdge).where(EntityEdge.fact.isnot(None))
        if group_id:
            stmt = stmt.where(EntityEdge.group_id == group_id)
        if missing_only:
            stmt = stmt.where(EntityEdge.fact_embedding.is_(None))

        edges = list(session.execute(stmt).scalars().all())
        logger.info("Edges to reindex: %d", len(edges))

        if not dry_run:
            for i in range(0, len(edges), batch_size):
                batch = edges[i : i + batch_size]
                texts = [e.fact for e in batch]
                embeddings = get_embeddings(texts, embedding_type="db")
                if len(embeddings) != len(batch):
                    logger.warning(
                        "Batch %d: expected %d embeddings, got %d — skipping",
                        i // batch_size,
                        len(batch),
                        len(embeddings),
                    )
                    continue
                for edge, emb in zip(batch, embeddings):
                    edge.fact_embedding = emb
                session.flush()
                logger.info("Edge batch %d/%d done", i // batch_size + 1, (len(edges) + batch_size - 1) // batch_size)

            session.commit()
            logger.info("Edge embeddings committed.")

    logger.info("Done. Entities=%d, Edges=%d, dry_run=%s", len(entities), len(edges), dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reindex entity/edge embeddings")
    parser.add_argument("--group", default=None, help="group_id to reindex (default: all)")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding API batch size")
    parser.add_argument("--dry-run", action="store_true", help="Show counts only, no writes")
    parser.add_argument("--missing-only", action="store_true", help="Only fill NULL embeddings")
    args = parser.parse_args()

    reindex(
        group_id=args.group,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        missing_only=args.missing_only,
    )
