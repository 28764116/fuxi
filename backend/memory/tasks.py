import logging
import uuid
from pathlib import Path

from worker import celery_app
from memory.neo4j_service import Neo4jGraphService

logger = logging.getLogger(__name__)


@celery_app.task(name="memory.process_document", bind=True)
def process_document(
    self,
    group_id: str,
    thread_id: str,
    file_path: str,
    file_name: str,
    language: str = "zh",
) -> dict:
    """Process a document file in chunks with progress tracking.

    参考 MiroFish 的分步处理模式:
    1. 解析文档 (10%)
    2. 分块 (20%)
    3. 逐块提取实体 (20-90%)
    4. 汇总 (100%)
    """
    from memory.file_parser import chunk_text, parse_file
    from memory.extractor import extract_triplets
    from memory.temporal import temporal_upsert
    from memory.embedder import get_embeddings
    from memory.models import Episode
    from app.database import sync_session_factory
    from datetime import datetime, timezone

    logger.info(f"Processing document: {file_name}")

    try:
        # 步骤1: 解析文档 (0-10%)
        self.update_state(state='PROGRESS', meta={
            'stage': '📄 正在解析文档',
            'progress': 5,
            'current': 0,
            'total': 0
        })

        text = parse_file(file_path)
        logger.info(f"Parsed document {file_name}: {len(text)} chars")

        # 步骤2: 智能分块 (10-20%)
        self.update_state(state='PROGRESS', meta={
            'stage': '✂️ 正在智能分段',
            'progress': 15,
            'current': 0,
            'total': 0
        })

        chunks = chunk_text(text)
        total_chunks = len(chunks)
        logger.info(f"Split into {total_chunks} chunks")

        if total_chunks == 0:
            return {
                'status': 'completed',
                'message': '文档为空或无有效内容',
                'entities_count': 0,
                'chunks_processed': 0
            }

        # 步骤3: 逐块处理 (20-90%) - 每块立即提交（真正的实时渲染）
        import time
        episodes_created = []
        total_triplets = 0
        total_entities = set()  # 跟踪唯一实体
        BATCH_SIZE = 1  # 每1个块 commit 一次（实时渲染）

        # 使用 Neo4j 服务（不需要手动 commit）
        neo4j_service = Neo4jGraphService()

        with sync_session_factory() as session:
            for i, chunk in enumerate(chunks):
                chunk_start = time.time()

                # 提取实体 (带上下文：前一个 chunk + 语言偏好)
                context = chunks[i-1][:150] if i > 0 else ""
                extract_start = time.time()
                triplets = extract_triplets(chunk, context=context, language=language)
                extract_time = time.time() - extract_start

                # 更新进度（包含实时统计）
                progress = 20 + int((i / total_chunks) * 70)
                self.update_state(state='PROGRESS', meta={
                    'stage': f'📝 处理块 {i+1}/{total_chunks}' + (f' ✓ 提取 {len(triplets)} 个三元组' if triplets else ''),
                    'progress': progress,
                    'current': i + 1,
                    'total': total_chunks,
                    'entities_count': len(total_entities),
                    'triplets_count': total_triplets,
                })

                # 创建 Episode
                episode = Episode(
                    group_id=group_id,
                    thread_id=uuid.UUID(thread_id),
                    role="system",
                    content=chunk,
                    source_type="document",
                    valid_at=datetime.now(timezone.utc),
                )
                session.add(episode)
                session.flush()
                episodes_created.append(str(episode.id))

                if triplets:
                    # 生成 embedding（可选：后续用于向量搜索）
                    embed_start = time.time()
                    facts = [t.fact for t in triplets]
                    fact_embeddings = get_embeddings(facts)
                    embed_time = time.time() - embed_start

                    # 写入 Neo4j
                    db_start = time.time()
                    for triplet in triplets:
                        try:
                            neo4j_service.temporal_upsert(
                                group_id=group_id,
                                triplet=triplet,
                                episode_id=str(episode.id),
                                valid_at=episode.valid_at
                            )
                            total_triplets += 1
                            # 跟踪唯一实体
                            total_entities.add(triplet.subject)
                            total_entities.add(triplet.object)
                        except Exception:
                            logger.exception(f"Failed to write triplet to Neo4j from chunk {i}")
                    db_time = time.time() - db_start
                else:
                    embed_time = 0
                    db_time = 0

                chunk_time = time.time() - chunk_start
                logger.info(
                    f"块 {i+1}/{total_chunks}: "
                    f"提取={extract_time:.1f}s, embedding={embed_time:.1f}s, "
                    f"数据库={db_time:.1f}s, 总计={chunk_time:.1f}s ({len(triplets)} 三元组)"
                )

                # PostgreSQL Episodes commit
                if (i + 1) % BATCH_SIZE == 0 or (i + 1) == total_chunks:
                    session.commit()  # 只 commit Episodes

        # 步骤4: 完成 (90-100%)
        self.update_state(state='PROGRESS', meta={
            'stage': '✅ 处理完成',
            'progress': 95,
            'current': total_chunks,
            'total': total_chunks
        })

        logger.info(
            f"Document {file_name} processed: {total_chunks} chunks, "
            f"{total_triplets} triplets extracted"
        )

        # 关闭 Neo4j 连接
        neo4j_service.close()

        # TODO: 异步更新实体摘要（待实现 Neo4j 版本）
        # update_entity_summaries.delay(group_id, list(total_entities))

        return {
            'status': 'completed',
            'message': f'成功处理文档：{file_name}',
            'entities_count': len(total_entities),
            'triplets_count': total_triplets,
            'chunks_processed': total_chunks,
            'episodes': episodes_created
        }

    except Exception as e:
        logger.exception(f"Document processing failed for {file_name}")
        return {
            'status': 'failed',
            'message': str(e),
            'entities_count': 0,
            'chunks_processed': 0
        }


@celery_app.task(name="memory.process_episode")
def process_episode(episode_id: str, language: str = "zh") -> None:
    """Process a newly ingested episode (using Neo4j).

    1. Read episode content from PostgreSQL
    2. Extract entity-relation triplets via LLM
    3. Write to Neo4j graph
    """
    from app.database import sync_session_factory
    from memory.extractor import extract_triplets
    from memory.models import Episode

    logger.info("Processing episode %s with language=%s", episode_id, language)

    neo4j_service = Neo4jGraphService()

    with sync_session_factory() as session:
        # 1. Load episode
        episode = session.get(Episode, uuid.UUID(episode_id))
        if not episode:
            logger.error("Episode %s not found", episode_id)
            return

        # 2. Build minimal context from recent episodes (only for pronoun resolution)
        from sqlalchemy import select

        ctx_stmt = (
            select(Episode)
            .where(
                Episode.thread_id == episode.thread_id,
                Episode.id != episode.id,
            )
            .order_by(Episode.valid_at.desc())
            .limit(2)  # 只取最近 2 条，减少上下文污染
        )
        recent = list(session.execute(ctx_stmt).scalars().all())
        recent.reverse()
        # 限制每条上下文的长度，避免过多信息（优化为150，减少污染）
        context_items = []
        for ep in recent:
            content = ep.content[:150] if len(ep.content) > 150 else ep.content
            context_items.append(f"[{ep.role}] {content}")
        context = "\n".join(context_items)

        # 3. Extract triplets with context and language preference
        triplets = extract_triplets(episode.content, context="", language=language)
        if not triplets:
            logger.info("No triplets extracted from episode %s", episode_id)
            neo4j_service.close()
            return

        # 4. Write to Neo4j
        for triplet in triplets:
            try:
                neo4j_service.temporal_upsert(
                    group_id=episode.group_id,
                    triplet=triplet,
                    episode_id=str(episode.id),
                    valid_at=episode.valid_at
                )
            except Exception:
                logger.exception("Failed to write triplet to Neo4j: %s", triplet.fact[:80])

        logger.info(
            "Episode %s processed: %d triplets written to Neo4j",
            episode_id,
            len(triplets),
        )

    # Close Neo4j connection
    neo4j_service.close()


@celery_app.task(name="memory.update_entity_summaries")
def update_entity_summaries(group_id: str, entity_names: list[str]) -> None:
    """Regenerate summaries and embeddings for a list of entities (async, post-extraction)."""
    from sqlalchemy import select

    from app.database import sync_session_factory
    from memory.embedder import get_embeddings
    from memory.extractor import summarize_entity
    from memory.models import Entity, EntityEdge

    with sync_session_factory() as session:
        entities_to_embed = []
        for name in entity_names:
            stmt = select(Entity).where(
                Entity.group_id == group_id,
                Entity.name == name,
            )
            entity = session.execute(stmt).scalars().first()
            if not entity:
                continue

            edge_stmt = (
                select(EntityEdge.fact)
                .where(
                    EntityEdge.group_id == group_id,
                    EntityEdge.expired_at.is_(None),
                    (EntityEdge.source_entity_id == entity.id)
                    | (EntityEdge.target_entity_id == entity.id),
                )
                .order_by(EntityEdge.valid_at.desc())
                .limit(20)
            )
            facts = list(session.execute(edge_stmt).scalars().all())

            if facts:
                entity.summary = summarize_entity(entity.name, entity.entity_type, facts)
                entities_to_embed.append(entity)

        session.flush()

        if entities_to_embed:
            summaries = [e.summary for e in entities_to_embed]
            embeddings = get_embeddings(summaries)
            if len(embeddings) == len(entities_to_embed):
                for entity, emb in zip(entities_to_embed, embeddings):
                    entity.summary_embedding = emb

        session.commit()
        logger.info("Updated summaries for %d entities in group %s", len(entities_to_embed), group_id)
