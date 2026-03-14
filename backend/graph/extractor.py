"""
LLM 实体关系提取模块
使用 LLM 从文本中提取实体和关系（并行版本，支持增量写入）
"""
import json
import re
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

from .llm_client import get_llm_client


@dataclass
class ExtractedEntity:
    """提取的实体"""
    name: str
    labels: List[str]
    summary: str = ""
    attributes: Dict[str, Any] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
        }


@dataclass
class ExtractedRelation:
    """提取的关系"""
    source: str
    target: str
    name: str
    fact: str = ""
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "name": self.name,
            "fact": self.fact,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
        }


class LLMExtractor:
    """LLM 实体关系提取器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client or get_llm_client()

    def extract(
        self,
        text: str,
        entity_types: List[Dict[str, Any]],
        edge_types: List[Dict[str, Any]],
        chunk_size: int = 800,
        overlap: int = 100,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int, List, List], None]] = None
    ) -> tuple:
        """从文本中提取实体和关系（并行版本，支持增量写入）"""
        entity_types_str = self._format_entity_types(entity_types)
        edge_types_str = self._format_edge_types(edge_types)

        system_prompt = f"""你是一个知识图谱提取专家。请严格从给定文本中提取实体和关系。

## 可用实体类型
{entity_types_str}

## 可用关系类型
{edge_types_str}

## 输出格式（严格JSON）
{{
    "entities": [
        {{"name": "实体的正式全称", "labels": ["实体类型"], "summary": "一句话描述该实体"}}
    ],
    "relations": [
        {{"source": "源实体名（必须与entities中的name完全一致）", "target": "目标实体名（必须与entities中的name完全一致）", "name": "关系类型", "fact": "该关系的具体事实描述"}}
    ]
}}

## 关键规则
1. **只提取文本中明确提到的**实体和关系，不要推测或编造
2. 实体名称必须使用文本中出现的**正式全称**，保持前后一致（如"武汉大学"不能写成"武大"）
3. 每个实体只出现一次，不要重复提取同一实体
4. 关系的 source 和 target 必须是你提取的实体名称，**完全一致**
5. labels 必须从上面的可用实体类型中选择
6. 关系的 name 必须从上面的可用关系类型中选择
7. 只返回纯 JSON，不要加任何解释"""

        chunks = self._split_text(text, chunk_size, overlap)
        total_chunks = len(chunks)

        all_entities = []
        all_relations = []

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._extract_single_chunk, chunk, system_prompt): i
                    for i, chunk in enumerate(chunks)
                }

                for future in as_completed(futures):
                    try:
                        chunk_idx = futures[future]
                        entities, relations = future.result()
                        all_entities.extend(entities)
                        all_relations.extend(relations)

                        if progress_callback:
                            progress_callback(chunk_idx, total_chunks, entities, relations)
                    except Exception as e:
                        logger.warning("并行提取失败: %s", e)
        except RuntimeError as e:
            logger.warning("并行提取失败，回退到单线程: %s", e)
            for i, chunk in enumerate(chunks):
                try:
                    entities, relations = self._extract_single_chunk(chunk, system_prompt)
                    all_entities.extend(entities)
                    all_relations.extend(relations)
                    if progress_callback:
                        progress_callback(i, total_chunks, entities, relations)
                except Exception as e:
                    logger.warning("提取失败: %s", e)

        return all_entities, all_relations

    def _format_entity_types(self, entity_types: List[Dict]) -> str:
        """格式化实体类型（包含描述和示例）"""
        if not entity_types:
            return "无限制"
        parts = []
        for e in entity_types:
            name = e.get('name', '')
            desc = e.get('description', '')
            examples = e.get('examples', [])
            line = f"- {name}: {desc}"
            if examples:
                line += f"（例: {', '.join(examples[:3])}）"
            parts.append(line)
        return "\n".join(parts)

    def _format_edge_types(self, edge_types: List[Dict]) -> str:
        """格式化关系类型（包含描述和方向约束）"""
        if not edge_types:
            return "无限制"
        parts = []
        for e in edge_types:
            name = e.get('name', '')
            desc = e.get('description', '')
            source_targets = e.get('source_targets', [])
            line = f"- {name}: {desc}"
            if source_targets:
                pairs = [f"{st.get('source', '?')}→{st.get('target', '?')}" for st in source_targets]
                line += f"（适用: {', '.join(pairs)}）"
            parts.append(line)
        return "\n".join(parts)

    def _split_text(self, text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
        """句子感知分块（在标点处断句，避免截断语义）"""
        if len(text) <= chunk_size:
            return [text]

        # 中文和英文标点断句符
        punct_chars = set('。！？；\n')

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            if end < len(text):
                # 在 chunk 后半段寻找最近的标点断句
                search_start = start + chunk_size // 2
                last_punct = -1
                for i in range(end - 1, search_start - 1, -1):
                    if text[i] in punct_chars:
                        last_punct = i
                        break
                if last_punct > search_start:
                    end = last_punct + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # 下一个块的起始位置（减去 overlap）
            start = end - overlap if end < len(text) else end

        return chunks

    def _extract_single_chunk(
        self,
        chunk: str,
        system_prompt: str
    ) -> tuple:
        """从单个文本块提取实体和关系"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请从以下文本中提取实体和关系：\n\n{chunk}"}
        ]

        try:
            result = self.llm.chat_json(messages, temperature=0.1)
            entities = result.get("entities", [])
            relations = result.get("relations", [])

            # 转换为标准格式
            extracted_entities = []
            for e in entities:
                name = e.get("name", "").strip()
                if not name:
                    continue
                labels = e.get("labels", [])
                if isinstance(labels, str):
                    labels = [labels]
                # 过滤空 labels
                labels = [l.strip() for l in labels if l and l.strip()]
                if not labels:
                    continue
                extracted_entities.append(ExtractedEntity(
                    name=name,
                    labels=labels,
                    summary=e.get("summary", ""),
                    attributes=e.get("attributes", {})
                ))

            extracted_relations = []
            # 构建当前块的实体名集合，用于校验关系端点
            entity_names_in_chunk = {e.name for e in extracted_entities}

            for r in relations:
                source = r.get("source", "").strip()
                target = r.get("target", "").strip()
                rel_name = r.get("name", "").strip()
                if not source or not target or not rel_name:
                    continue
                # 校验关系两端实体是否存在于当前块提取结果
                if source not in entity_names_in_chunk or target not in entity_names_in_chunk:
                    logger.debug("跳过关系 %s->%s: 端点不在当前块实体中", source, target)
                    continue
                # 排除自环
                if source == target:
                    continue
                extracted_relations.append(ExtractedRelation(
                    source=source,
                    target=target,
                    name=rel_name,
                    fact=r.get("fact", "")
                ))

            return extracted_entities, extracted_relations

        except Exception as e:
            logger.warning("单块提取失败: %s", e)
            return [], []
