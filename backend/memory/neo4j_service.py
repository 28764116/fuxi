"""
Neo4j 图谱服务（参考 MiroFish neo4j_graph_builder.py）
负责实体和关系的增量写入、temporal 管理
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from graph.client import Neo4jClient, GraphNode, GraphEdge
from memory.extractor import Triplet

logger = logging.getLogger(__name__)


class Neo4jGraphService:
    """Neo4j 图谱服务"""

    def __init__(self, client: Optional[Neo4jClient] = None):
        self.client = client or Neo4jClient()

    def ensure_graph_exists(self, group_id: str):
        """确保 Graph 节点存在"""
        with self.client.driver.session(database=self.client.database) as session:
            result = session.run(
                "MATCH (g:Graph {graph_id: $graph_id}) RETURN g",
                graph_id=group_id
            )
            if not result.single():
                # 创建 Graph 节点
                self.client.create_graph(group_id, f"Group {group_id}")

    def close(self):
        """关闭连接"""
        self.client.close()

    def get_or_create_entity(
        self,
        group_id: str,
        name: str,
        entity_type: str,
        summary: str = ""
    ) -> str:
        """获取或创建实体，返回 UUID"""
        # 检查是否存在
        existing_uuid = self.client.node_exists(group_id, name)
        if existing_uuid:
            return existing_uuid

        # 创建新实体
        entity_uuid = str(uuid.uuid4())
        node = GraphNode(
            uuid=entity_uuid,
            name=name,
            labels=[entity_type],
            summary=summary,
            attributes={}
        )
        self.client.add_node(group_id, node)
        logger.info(f"Created entity: {name} ({entity_type})")
        return entity_uuid

    def temporal_upsert(
        self,
        group_id: str,
        triplet: Triplet,
        episode_id: str,
        valid_at: datetime
    ) -> str:
        """Temporal upsert: 创建或更新关系（支持时序语义）

        逻辑简化版（参考 MiroFish）：
        1. 获取或创建 source/target 实体
        2. 检查是否存在相同的活跃关系 (source, target, predicate, expired_at IS NULL)
        3. 如果存在：更新 episode_ids
        4. 如果不存在：创建新关系
        """
        # 0. 确保 Graph 存在
        self.ensure_graph_exists(group_id)

        # 1. 获取或创建实体
        source_uuid = self.get_or_create_entity(
            group_id,
            triplet.subject,
            triplet.subject_type,
            triplet.subject_summary
        )
        target_uuid = self.get_or_create_entity(
            group_id,
            triplet.object,
            triplet.object_type,
            triplet.object_summary
        )

        # 2. 检查是否存在相同的活跃关系
        existing_edge = self._find_active_edge(
            group_id, source_uuid, target_uuid, triplet.predicate
        )

        if existing_edge:
            # 更新 episode_ids
            edge_uuid = existing_edge["uuid"]
            episode_ids = existing_edge.get("episode_ids", [])
            if episode_id not in episode_ids:
                episode_ids.append(episode_id)
                self._update_edge_episodes(group_id, edge_uuid, episode_ids)
            logger.info(f"Updated edge: {triplet.subject} → {triplet.object} ({triplet.predicate})")
            return edge_uuid

        # 3. 创建新关系
        edge_uuid = str(uuid.uuid4())
        edge = GraphEdge(
            uuid=edge_uuid,
            name=triplet.predicate,
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            source_node_name=triplet.subject,
            target_node_name=triplet.object,
            fact=triplet.fact,
            valid_at=valid_at.isoformat(),
            expired_at=None,
            episodes=[episode_id]
        )
        self.client.add_edge(group_id, edge)
        logger.info(f"Created edge: {triplet.subject} → {triplet.object} ({triplet.predicate})")
        return edge_uuid

    def _find_active_edge(
        self,
        group_id: str,
        source_uuid: str,
        target_uuid: str,
        predicate: str
    ) -> Optional[Dict[str, Any]]:
        """查找活跃边（expired_at IS NULL）"""
        with self.client.driver.session(database=self.client.database) as session:
            result = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(s:Entity {uuid: $source_uuid})
                MATCH (g)<-[:BELONGS_TO]-(t:Entity {uuid: $target_uuid})
                MATCH (s)-[r:RELATES {name: $predicate}]->(t)
                WHERE r.expired_at IS NULL
                RETURN r.uuid as uuid, r.episode_ids as episode_ids, r.fact as fact
                LIMIT 1
                """,
                graph_id=group_id,
                source_uuid=source_uuid,
                target_uuid=target_uuid,
                predicate=predicate
            )
            record = result.single()
            return dict(record) if record else None

    def _update_edge_episodes(
        self,
        group_id: str,
        edge_uuid: str,
        episode_ids: List[str]
    ):
        """更新关系的 episode_ids"""
        with self.client.driver.session(database=self.client.database) as session:
            session.run(
                """
                MATCH ()-[r:RELATES {uuid: $edge_uuid}]->()
                SET r.episode_ids = $episode_ids
                """,
                edge_uuid=edge_uuid,
                episode_ids=episode_ids
            )

    def batch_write_triplets(
        self,
        group_id: str,
        triplets: List[Triplet],
        episode_id: str,
        valid_at: datetime
    ):
        """批量写入三元组（增量方式）"""
        for triplet in triplets:
            try:
                self.temporal_upsert(group_id, triplet, episode_id, valid_at)
            except Exception as e:
                logger.error(f"Failed to write triplet: {triplet.fact[:50]}, error: {e}")
                continue

    def get_all_entities(self, group_id: str) -> List[Dict[str, Any]]:
        """获取所有实体（格式兼容前端）"""
        nodes = self.client.get_nodes(group_id)
        entities = []
        for node in nodes:
            # 提取实体类型（labels 中除了 'Entity'）
            labels = node.get("labels", [])
            entity_type = next((l for l in labels if l != "Entity"), "concept")

            entities.append({
                "id": node["uuid"],  # 前端期望字符串 UUID
                "name": node["name"],
                "entity_type": entity_type,
                "summary": node.get("summary", ""),
                "display_name": node["name"],
                # 可选字段（前端不强制要求）
                "group_id": group_id,
                "created_at": node.get("created_at"),
                "updated_at": node.get("created_at")  # Neo4j 没有 updated_at
            })
        return entities

    def get_all_edges(
        self,
        group_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """获取所有边"""
        with self.client.driver.session(database=self.client.database) as session:
            cypher = """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(s:Entity)
                MATCH (g)<-[:BELONGS_TO]-(t:Entity)
                MATCH (s)-[r:RELATES]->(t)
            """
            if active_only:
                cypher += " WHERE r.expired_at IS NULL"

            cypher += """
                RETURN r.uuid as id,
                       r.name as predicate,
                       s.uuid as source_entity_id,
                       t.uuid as target_entity_id,
                       r.fact as fact,
                       r.valid_at as valid_at,
                       r.expired_at as expired_at,
                       r.episode_ids as episode_ids,
                       r.created_at as created_at
            """

            result = session.run(cypher, graph_id=group_id)
            edges = []
            for record in result:
                edges.append({
                    "id": record["id"],  # UUID 字符串
                    "predicate": record["predicate"],
                    "source_entity_id": record["source_entity_id"],
                    "target_entity_id": record["target_entity_id"],
                    "fact": record["fact"] or "",
                    "valid_at": record.get("valid_at"),
                    "expired_at": record.get("expired_at"),
                    "episode_ids": record.get("episode_ids", []),
                    "created_at": record.get("created_at"),
                    # 可选字段
                    "group_id": group_id
                })
            return edges
