"""
Neo4j 客户端
基于图数据库的知识图谱存储
"""
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

from neo4j import GraphDatabase
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """图谱节点（兼容 Zep EntityNode 格式）"""
    uuid: str
    name: str
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """获取实体类型"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class GraphEdge:
    """图谱边（兼容 Zep Edge 格式）"""
    uuid: str
    name: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: str = ""
    target_node_name: str = ""
    fact: str = ""
    fact_type: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    episodes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "fact": self.fact,
            "fact_type": self.fact_type or self.name,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at,
            "episodes": self.episodes,
        }


class Neo4jClient:
    """Neo4j 客户端"""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None, database: str = None):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_username
        self.password = password or settings.neo4j_password
        self.database = database or settings.neo4j_database
        
        if not self.password:
            raise ValueError("NEO4J_PASSWORD 未配置")
        
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )
        self._ensure_indexes()

    def _ensure_indexes(self):
        """创建 Neo4j 约束和索引以提升查询性能"""
        try:
            with self.driver.session(database=self.database) as session:
                session.run("CREATE INDEX IF NOT EXISTS FOR (g:Graph) ON (g.graph_id)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.uuid)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)")
        except Exception as e:
            logger.warning("创建 Neo4j 索引失败（可忽略）: %s", e)

    def close(self):
        self.driver.close()
    
    def create_graph(self, graph_id: str, name: str) -> str:
        """创建图谱"""
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                CREATE (g:Graph {graph_id: $graph_id, name: $name, created_at: datetime()})
                """,
                graph_id=graph_id,
                name=name
            )
        return graph_id
    
    def delete_graph(self, graph_id: str):
        """删除图谱"""
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})
                OPTIONAL MATCH (g)<-[:BELONGS_TO]-(n:Entity)
                OPTIONAL MATCH (n)-[r]->(m:Entity)
                WHERE n:BELONGS_TO OR m:BELONGS_TO
                DETACH DELETE r
                DETACH DELETE n
                DETACH DELETE g
                """,
                graph_id=graph_id
            )
    
    def add_node(self, graph_id: str, node: GraphNode) -> GraphNode:
        """添加节点"""
        with self.driver.session(database=self.database) as session:
            label_set = set(node.labels) if node.labels else set()
            label_set.add("Entity")
            labels = ":".join(sorted(label_set))
            session.run(
                f"""
                MATCH (g:Graph {{graph_id: $graph_id}})
                CREATE (n:{labels} {{uuid: $uuid, name: $name, summary: $summary, attributes: $attributes, created_at: datetime()}})
                CREATE (g)<-[:BELONGS_TO]-(n)
                """,
                graph_id=graph_id,
                uuid=node.uuid,
                name=node.name,
                summary=node.summary,
                attributes=json.dumps(node.attributes, ensure_ascii=False) if node.attributes else "{}"
            )
        node.created_at = datetime.now().isoformat()
        return node
    
    def add_edge(self, graph_id: str, edge: GraphEdge) -> GraphEdge:
        """添加边（支持 temporal 字段）"""
        with self.driver.session(database=self.database) as session:
            # Convert datetime to ISO string for Neo4j
            valid_at_str = edge.valid_at if edge.valid_at else datetime.now().isoformat()
            expired_at_str = edge.expired_at if edge.expired_at else None

            session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})
                MATCH (g)<-[:BELONGS_TO]-(s:Entity {uuid: $source_uuid})
                MATCH (g)<-[:BELONGS_TO]-(t:Entity {uuid: $target_uuid})
                CREATE (s)-[r:RELATES {
                    uuid: $uuid,
                    name: $name,
                    fact: $fact,
                    created_at: datetime(),
                    valid_at: $valid_at,
                    expired_at: $expired_at,
                    episode_ids: $episode_ids
                }]->(t)
                """,
                graph_id=graph_id,
                uuid=edge.uuid,
                source_uuid=edge.source_node_uuid,
                target_uuid=edge.target_node_uuid,
                name=edge.name,
                fact=edge.fact,
                valid_at=valid_at_str,
                expired_at=expired_at_str,
                episode_ids=edge.episodes or []
            )
        edge.created_at = datetime.now().isoformat()
        return edge
    
    def get_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取所有节点"""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(n:Entity)
                RETURN n.uuid as uuid, n.name as name, labels(n) as labels, 
                       n.summary as summary, n.attributes as attributes,
                       n.created_at as created_at
                """,
                graph_id=graph_id
            )
            return [dict(record) for record in result]
    
    def get_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取所有边"""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(s:Entity)-[r:RELATES]->(t:Entity)-[:BELONGS_TO]->(g)
                RETURN r.uuid as uuid, r.name as name,
                       s.uuid as source_node_uuid, s.name as source_name,
                       t.uuid as target_node_uuid, t.name as target_name,
                       r.fact as fact, r.created_at as created_at
                """,
                graph_id=graph_id
            )
            return [dict(record) for record in result]
    
    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        """获取图谱信息"""
        with self.driver.session(database=self.database) as session:
            # 节点数
            node_record = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(n:Entity)
                RETURN count(n) as count
                """,
                graph_id=graph_id
            ).single()
            node_count = node_record["count"] if node_record else 0

            # 边数
            edge_record = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(s:Entity)
                MATCH (s)-[r:RELATES]->(t:Entity)
                RETURN count(r) as count
                """,
                graph_id=graph_id
            ).single()
            edge_count = edge_record["count"] if edge_record else 0

            # 实体类型
            type_record = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(n:Entity)
                UNWIND labels(n) as label
                WITH label WHERE label <> 'Entity'
                RETURN collect(DISTINCT label) as types
                """,
                graph_id=graph_id
            ).single()
            entity_types = type_record["types"] if type_record else []
            
            return {
                "graph_id": graph_id,
                "node_count": node_count,
                "edge_count": edge_count,
                "entity_types": entity_types
            }
    
    def node_exists(self, graph_id: str, name: str) -> Optional[str]:
        """检查节点是否存在"""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(n:Entity {name: $name})
                RETURN n.uuid as uuid
                """,
                graph_id=graph_id,
                name=name
            )
            record = result.single()
            return record["uuid"] if record else None

    def batch_node_uuids(self, graph_id: str, names: List[str]) -> Dict[str, str]:
        """批量查询节点 UUID，返回 {name: uuid} 映射"""
        if not names:
            return {}
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (g:Graph {graph_id: $graph_id})<-[:BELONGS_TO]-(n:Entity)
                WHERE n.name IN $names
                RETURN n.name as name, n.uuid as uuid
                """,
                graph_id=graph_id,
                names=names
            )
            return {record["name"]: record["uuid"] for record in result}
