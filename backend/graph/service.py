"""
图谱服务
使用 LLM 从文本中提取实体和关系，构建知识图谱
支持增量写入和异步构建
"""
import uuid
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Callable

from .client import Neo4jClient, GraphNode, GraphEdge

logger = logging.getLogger(__name__)
from .llm_client import get_llm_client
from .extractor import LLMExtractor, ExtractedEntity, ExtractedRelation


class GraphService:
    """图谱服务"""
    
    EXTRACT_PROMPT = """你是一个知识图谱专家。请从以下文本中提取实体和关系。

本体定义：
{ontology}

文本：
{text}

请以 JSON 格式返回提取的实体和关系：
{{
    "entities": [
        {{"name": "实体名称", "labels": ["实体类型"], "summary": "实体摘要"}}
    ],
    "relations": [
        {{"source": "源实体名称", "target": "目标实体名称", "name": "关系类型", "fact": "关系描述"}}
    ]
}}

只返回 JSON，不要有其他内容。"""

    def __init__(self):
        self.neo4j = Neo4jClient()
        self.llm = get_llm_client()
        self.extractor = LLMExtractor(self.llm)
    
    def create_graph(self, name: str, graph_id: str = None) -> str:
        """创建图谱"""
        if not graph_id:
            graph_id = f"fuxi_{uuid.uuid4().hex[:12]}"
        self.neo4j.create_graph(graph_id, name)
        return graph_id
    
    def delete_graph(self, graph_id: str):
        """删除图谱"""
        self.neo4j.delete_graph(graph_id)
    
    def build_graph_async(
        self,
        graph_id: str,
        text: str,
        ontology: Dict[str, Any],
        chunk_size: int = 500,
        overlap: int = 50,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ):
        """异步构建图谱（后台线程，非阻塞）
        
        Args:
            graph_id: 图谱ID
            text: 输入文本
            ontology: 本体定义
            chunk_size: 文本块大小
            overlap: 块重叠大小
            max_workers: 并行worker数
            progress_callback: 进度回调 (message, progress)
        """
        # 获取实体和关系类型
        entity_types = ontology.get("entity_types", [])
        edge_types = ontology.get("edge_types", [])
        
        # 启动后台线程
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(
                graph_id, text, entity_types, edge_types,
                chunk_size, overlap, max_workers, progress_callback
            )
        )
        thread.daemon = True
        thread.start()
        
        return graph_id
    
    def build_graph(
        self,
        graph_id: str,
        text: str,
        ontology: Dict[str, Any],
        chunk_size: int = 500,
        overlap: int = 50,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ):
        """同步构建图谱（在当前线程执行）"""
        entity_types = ontology.get("entity_types", [])
        edge_types = ontology.get("edge_types", [])
        
        self._build_graph_worker(
            graph_id, text, entity_types, edge_types,
            chunk_size, overlap, max_workers, progress_callback
        )
    
    def _build_graph_worker(
        self,
        graph_id: str,
        text: str,
        entity_types: List[Dict],
        edge_types: List[Dict],
        chunk_size: int,
        overlap: int,
        max_workers: int,
        progress_callback: Optional[Callable]
    ):
        """后台构建图谱（增量写入）"""
        try:
            total_chars = len(text)
            total_chunks = len(self.extractor._split_text(text, chunk_size, overlap))
            
            # 跟踪已写入的实体和关系
            written_entities = {}  # (name, labels) -> entity
            written_entity_names = set()
            
            def incremental_callback(chunk_idx: int, total: int, entities: List[ExtractedEntity], relations: List[ExtractedRelation]):
                """增量回调：每处理完一个块立即写入"""
                nonlocal written_entities, written_entity_names
                
                # 去重并合并新提取的实体
                new_entities = []
                for e in entities:
                    key = (e.name, tuple(sorted(e.labels)))
                    if key not in written_entities:
                        written_entities[key] = e
                        written_entity_names.add(e.name)
                        new_entities.append(e)
                
                # 立即写入新实体
                if new_entities:
                    self._write_entities(graph_id, new_entities)
                
                # 过滤出有效关系（两端实体都存在）
                new_relations = []
                for r in relations:
                    if r.source in written_entity_names and r.target in written_entity_names:
                        new_relations.append(r)
                
                # 立即写入新关系
                if new_relations:
                    entity_list = list(written_entities.values())
                    self._write_relations(graph_id, new_relations, entity_list)
                
                # 进度回调
                if progress_callback:
                    progress_msg = f"处理块 {chunk_idx + 1}/{total}，已写入 {len(written_entities)} 实体"
                    progress_val = 0.9 * ((chunk_idx + 1) / total)
                    progress_callback(progress_msg, progress_val)
            
            # 使用 LLM 提取器（带增量回调）
            final_entities, final_relations = self.extractor.extract(
                text=text,
                entity_types=entity_types,
                edge_types=edge_types,
                chunk_size=chunk_size,
                overlap=overlap,
                max_workers=max_workers,
                progress_callback=incremental_callback
            )
            
            # 完成
            if progress_callback:
                progress_callback(
                    f"图谱构建完成: {len(written_entities)} 个实体",
                    1.0
                )
            
            logger.info("图谱 %s 构建完成: %d 实体", graph_id, len(written_entities))

        except Exception as e:
            logger.exception("图谱构建失败")
            if progress_callback:
                progress_callback(f"构建失败: {str(e)}", 0)
    
    def _write_entities(self, graph_id: str, entities: List[ExtractedEntity]):
        """写入实体节点"""
        if not entities:
            return
        
        for entity in entities:
            entity_uuid = str(uuid.uuid4())
            node = GraphNode(
                uuid=entity_uuid,
                name=entity.name,
                labels=entity.labels,
                summary=entity.summary,
                attributes=entity.attributes
            )
            self.neo4j.add_node(graph_id, node)
    
    def _write_relations(self, graph_id: str, relations: List[ExtractedRelation], entities: List[ExtractedEntity]):
        """写入关系边"""
        if not relations:
            return

        # 批量查询所有相关实体的 UUID，避免 N 次数据库查询
        needed_names = set()
        for rel in relations:
            needed_names.add(rel.source)
            needed_names.add(rel.target)
        name_to_uuid = self.neo4j.batch_node_uuids(graph_id, list(needed_names))

        for rel in relations:
            source_uuid = name_to_uuid.get(rel.source)
            target_uuid = name_to_uuid.get(rel.target)

            if source_uuid and target_uuid:
                edge = GraphEdge(
                    uuid=str(uuid.uuid4()),
                    name=rel.name,
                    source_node_uuid=source_uuid,
                    target_node_uuid=target_uuid,
                    fact=rel.fact
                )
                self.neo4j.add_edge(graph_id, edge)
            else:
                logger.debug(
                    "跳过关系 %s->%s: 节点不存在 (source=%s, target=%s)",
                    rel.source, rel.target, bool(source_uuid), bool(target_uuid)
                )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """获取图谱数据"""
        info = self.neo4j.get_graph_info(graph_id)
        nodes = self.neo4j.get_nodes(graph_id)
        edges = self.neo4j.get_edges(graph_id)
        
        # 格式化节点
        formatted_nodes = []
        for node in nodes:
            labels = node.get("labels", [])
            entity_type = next((l for l in labels if l != "Entity"), "Unknown")
            created_at = node.get("created_at")
            formatted_nodes.append({
                "uuid": node["uuid"],
                "name": node["name"],
                "entity_type": entity_type,
                "labels": labels,
                "summary": node.get("summary", ""),
                "attributes": json.loads(node["attributes"]) if isinstance(node.get("attributes"), str) else (node.get("attributes") or {}),
                "created_at": str(created_at) if created_at else None
            })

        # 格式化边
        formatted_edges = []
        for edge in edges:
            created_at = edge.get("created_at")
            formatted_edges.append({
                "uuid": edge["uuid"],
                "name": edge["name"],
                "source_node_uuid": edge["source_node_uuid"],
                "source_name": edge.get("source_name", ""),
                "target_node_uuid": edge["target_node_uuid"],
                "target_name": edge.get("target_name", ""),
                "fact": edge.get("fact", ""),
                "created_at": str(created_at) if created_at else None
            })
        
        return {
            "graph_id": graph_id,
            "node_count": info["node_count"],
            "edge_count": info["edge_count"],
            "entity_types": info["entity_types"],
            "nodes": formatted_nodes,
            "edges": formatted_edges
        }
    
    def _split_text(self, text: str, chunk_size: int = 2000) -> List[str]:
        """分块文本"""
        # 按段落分割
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        
        for para in paragraphs:
            if len(current) + len(para) < chunk_size:
                current += para + "\n\n"
            else:
                if current:
                    chunks.append(current.strip())
                current = para + "\n\n"
        
        if current:
            chunks.append(current.strip())
        
        return chunks if chunks else [text]
    
    def _extract_from_chunk(
        self,
        text: str,
        ontology: Dict[str, Any]
    ) -> tuple:
        """从文本块提取实体和关系"""
        
        entity_types = ontology.get("entity_types", [])
        edge_types = ontology.get("edge_types", [])
        
        ontology_str = f"实体类型: {', '.join(entity_types)}\n关系类型: {', '.join(edge_types)}"
        
        messages = [
            {"role": "system", "content": "你是一个知识图谱专家，擅长从文本中提取结构化的实体和关系。"},
            {"role": "user", "content": self.EXTRACT_PROMPT.format(
                ontology=ontology_str,
                text=text[:3000]  # 限制文本长度
            )}
        ]
        
        try:
            result = self.llm.chat_json(messages)
            entities = result.get("entities", [])
            relations = result.get("relations", [])
            return entities, relations
        except Exception as e:
            logger.warning("LLM 提取失败: %s", e)
            return [], []
    
