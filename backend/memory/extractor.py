"""LLM-based entity/relation triplet extraction from text."""

import json
import logging
import re
from dataclasses import dataclass, field

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def _clean_llm_output(text: str) -> str:
    """Remove <think> blocks and markdown code fences from LLM output."""
    if not text:
        return text
    # Remove closed <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Handle unclosed <think> blocks (output truncated by max_tokens)
    if '<think>' in text:
        idx = text.find('<think>')
        after = text[idx + len('<think>'):].strip()
        before = text[:idx].strip()
        # Prefer content after <think> (reasoning truncated, JSON follows)
        text = after if after else before
    # Remove markdown code blocks
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _fix_json_string(json_str: str) -> str:
    """Multi-level JSON repair strategy (from MiroFish + custom fixes).

    1. Extract outermost JSON object
    2. Clean illegal control chars inside strings with state machine
    3. Fix bracket misuse: ) → } outside strings
    4. Fix missing object brackets: },"field": → },{"field":
    """
    # 1. Extract outermost JSON object
    match = re.search(r'\{[\s\S]*\}', json_str)
    if match:
        json_str = match.group()

    # 2. State machine: clean illegal control chars inside strings
    fixed_chars = []
    in_string = False
    escape_next = False
    for ch in json_str:
        if escape_next:
            fixed_chars.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            fixed_chars.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            fixed_chars.append(ch)
        elif in_string and ord(ch) < 0x20 and ch not in ('\t', '\n', '\r'):
            # Replace control chars with space
            fixed_chars.append(' ')
        elif in_string and ch in ('\n', '\r', '\t'):
            # Replace newlines/tabs with space
            fixed_chars.append(' ')
        else:
            fixed_chars.append(ch)
    json_str = ''.join(fixed_chars)

    # 3. Fix bracket misuse: ) → } outside strings
    result_chars = []
    in_string = False
    escape_next = False
    for ch in json_str:
        if escape_next:
            result_chars.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            result_chars.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result_chars.append(ch)
        elif not in_string and ch == ')':
            result_chars.append('}')
        else:
            result_chars.append(ch)
    json_str = ''.join(result_chars)

    # 4. Fix missing/extra brackets and quotes in arrays
    # Pattern 1: },"field": → },{"field": (missing opening brace)
    json_str = re.sub(r'\},\s*"(\w+)":', r'},{"\\1":', json_str)

    # Pattern 2: },"{" → },{ (extra quote before opening brace)
    json_str = re.sub(r'\},\s*"\{', r',{', json_str)

    # Pattern 3: }"{ → },{ (missing comma, extra quote)
    json_str = re.sub(r'\}"\{', r'},{', json_str)

    return json_str


EXTRACTION_PROMPT_TEMPLATE = """\
You are a knowledge graph extraction engine. Extract entities and relationships from the given text.

**IMPORTANT: Output language is {language}. ALL text fields (entity names, summaries, relation facts) MUST be in {language}.**

## Output format
Return ONLY a JSON object with entities and relations. No other text, no markdown fences.

```json
{
  "entities": [
    {
      "name": "entity name",
      "type": "entity type",
      "summary": "brief description of this entity (max 50 chars)"
    }
  ],
  "relations": [
    {
      "source": "source entity name",
      "target": "target entity name",
      "type": "relationship type",
      "fact": "detailed description of this relationship (max 100 chars)"
    }
  ]
}
```

## Field rules
- Entity name: Use the most canonical, complete name in **{language}**.
  • If language is "zh": Use Chinese names (e.g., "埃隆·马斯克" not "Elon Musk", "特斯拉" not "Tesla", "苹果公司" not "Apple")
  • If language is "en": Use English names (e.g., "Elon Musk" not "马斯克", "Tesla" not "特斯拉", "Apple Inc." not "苹果")
  • Never use pronouns (e.g., "he/she/it/他/她/它") or generic terms ("该公司/the company")
  • For the same entity across documents, ALWAYS use the SAME name to avoid duplicates.
- Entity type: Choose a general, reusable type. Use snake_case, singular form, in English. **Avoid overly specific types** (e.g., use "military" not "military_unit" or "missile_system").
  Preferred types (use these whenever possible):
  • person, organization, location, country
  • concept, event, product, policy
  • technology, military, currency, law
  • agreement, industry, time
  Only create a new type if absolutely necessary and none of the above fit.
- Entity summary: A concise description (max 50 chars), e.g., "Co-founder and CEO of Tesla and SpaceX"
- Relation type: Use a concise snake_case verb from the preferred vocabulary below. Only invent a new one if none fit.
- Relation fact: A detailed sentence (max 100 chars), e.g., "Elon Musk co-founded Tesla Motors in 2003 and serves as CEO"

## Preferred relationship vocabulary
Person–Org:   works_at, founded, leads, invested_in, acquired_by, studied_at, member_of
Person–Place: born_in, lives_in, visited
Person–Person: married_to, parent_of, child_of, reports_to, collaborated_with
Org–Org:      acquired, partnered_with, competes_with, subsidiary_of, invested_in
Org–Place:    headquartered_in, operates_in
Org–Product:  developed, owns, launched
Event:        caused_by, happened_in, happened_at, participated_in, resulted_in
General:      related_to, part_of, supports, opposes, uses, created

## Critical rules
1. Extract ONLY concrete, verifiable facts — no opinions, predictions, or speculation.
2. Extract ONLY from the [Current text] section — DO NOT extract facts from [Previous context].
3. Use [Previous context] ONLY to resolve pronouns (I/me/we/he/she/他/她/它) to actual entity names.
4. Resolve ALL pronouns to the actual entity name using context.
5. Never use generic placeholders ("用户","说话者","speaker","the company") as entity names.
6. If the same entity appears with multiple names/aliases, always use its most complete canonical name.
7. Every entity MUST have a non-empty summary; every relation MUST have a detailed fact description.
8. If no factual entities/relations can be extracted from [Current text], return {"entities": [], "relations": []}.

## Examples
Text: "马云于1999年在杭州创立了阿里巴巴集团，该公司总部位于杭州，并于2014年在纽约证券交易所上市。"
Output:
{
  "entities": [
    {"name": "马云", "type": "person", "summary": "阿里巴巴集团创始人"},
    {"name": "阿里巴巴集团", "type": "organization", "summary": "中国电子商务巨头，1999年创立于杭州"},
    {"name": "杭州", "type": "location", "summary": "浙江省省会，阿里巴巴总部所在地"}
  ],
  "relations": [
    {"source": "马云", "target": "阿里巴巴集团", "type": "founded", "fact": "马云于1999年创立了阿里巴巴集团"},
    {"source": "阿里巴巴集团", "target": "杭州", "type": "headquartered_in", "fact": "阿里巴巴集团总部位于杭州"},
    {"source": "阿里巴巴集团", "target": "纽约证券交易所", "type": "listed_at", "fact": "阿里巴巴集团于2014年在纽约证券交易所上市"}
  ]
}

Text: "OpenAI was founded in 2015 by Sam Altman, Elon Musk and others. In 2019, Microsoft invested $1 billion in OpenAI."
Output:
{
  "entities": [
    {"name": "Sam Altman", "type": "person", "summary": "Co-founder of OpenAI, current CEO"},
    {"name": "Elon Musk", "type": "person", "summary": "Co-founder of OpenAI, Tesla and SpaceX CEO"},
    {"name": "OpenAI", "type": "organization", "summary": "AI research company founded in 2015"},
    {"name": "Microsoft", "type": "organization", "summary": "Technology corporation, major OpenAI investor"}
  ],
  "relations": [
    {"source": "Sam Altman", "target": "OpenAI", "type": "founded", "fact": "Sam Altman co-founded OpenAI in 2015"},
    {"source": "Elon Musk", "target": "OpenAI", "type": "founded", "fact": "Elon Musk co-founded OpenAI in 2015"},
    {"source": "Microsoft", "target": "OpenAI", "type": "invested_in", "fact": "Microsoft invested $1 billion in OpenAI in 2019"}
  ]
}
"""

GOAL_EXTRACTION_SUFFIX = """\

IMPORTANT — GOAL-DIRECTED EXTRACTION:
The user has a specific analytical goal: {goal}
Prioritize extracting triplets that are DIRECTLY relevant to this goal.
Still extract all factual triplets, but if you must limit scope, prefer those relevant to the goal.
"""


# 中文类型名 → 英文规范化映射（兜底，避免模型返回中文）
_TYPE_NORMALIZE: dict[str, str] = {
    "人物": "person", "人": "person", "个人": "person",
    "组织": "organization", "机构": "organization", "公司": "organization", "企业": "organization",
    "地点": "location", "地区": "region", "地方": "location", "城市": "city",
    "国家": "country", "政府": "government",
    "概念": "concept", "理论": "concept",
    "事件": "event", "活动": "event",
    "产品": "product", "软件": "product", "系统": "product",
    "政策": "policy", "法规": "law", "制度": "policy",
    "时间": "time", "日期": "time",
    "军事": "military", "部队": "military", "武器": "military",
    "技术": "technology", "科技": "technology",
    "货币": "currency", "资金": "currency",
    "协议": "agreement", "条约": "agreement",
    "行业": "industry", "产业": "industry",
}


def _normalize_entity_type(raw: str) -> str:
    """Normalize entity type: convert Chinese to English, merge overly specific types.

    We normalize to general categories to avoid type explosion.
    """
    t = raw.strip().lower().replace(" ", "_")  # Convert spaces to underscores

    # If it's Chinese, try to translate
    if t in _TYPE_NORMALIZE:
        t = _TYPE_NORMALIZE[t]

    # Merge overly specific types to general categories
    # Military: military_unit, missile_system, military_base, weapon, army, navy, air_force → military
    if any(keyword in t for keyword in ['military', 'weapon', 'missile', 'army', 'navy', 'air_force', 'defense', 'soldier']):
        return "military"

    # Technology: ai_technology, computer_technology, software_technology → technology
    if 'technology' in t or 'tech' in t or t in ['software', 'hardware', 'system', 'platform']:
        return "technology"

    # Agreement: trade_agreement, peace_treaty, contract → agreement
    if any(keyword in t for keyword in ['agreement', 'treaty', 'contract', 'accord', 'pact']):
        return "agreement"

    # Location: city, province, region, area → location
    if t in ['city', 'province', 'region', 'area', 'place', 'district']:
        return "location"

    # Organization: company, corporation, institution, agency → organization
    if t in ['company', 'corporation', 'institution', 'agency', 'firm', 'enterprise']:
        return "organization"

    # Otherwise, keep the original type if it's already general
    return t if t else "concept"


@dataclass
class Triplet:
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str
    fact: str
    subject_summary: str = ""  # Entity summary for subject
    object_summary: str = ""   # Entity summary for object
    confidence: float = field(default=1.0)


ENTITY_SUMMARY_PROMPT = """\
You are a knowledge graph summarizer. Given an entity and its related facts, \
generate a concise, informative summary of the entity.

Rules:
1. Summarize ALL key facts about the entity into 2-4 sentences.
2. Prioritize the most important and recent information.
3. Write in the same language as the facts (Chinese facts → Chinese summary).
4. Be factual — do not add speculation or opinions.
5. If facts contradict each other, prefer the more recent one.
6. Return ONLY the summary text, no other formatting.
"""


def summarize_entity(
    entity_name: str, entity_type: str, facts: list[str]
) -> str:
    """Call LLM to generate a concise entity summary from its active facts."""
    if not facts:
        return f"{entity_name} ({entity_type})"

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    facts_text = "\n".join(f"- {f}" for f in facts)
    user_message = f"Entity: {entity_name} (type: {entity_type})\n\nFacts:\n{facts_text}"

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": ENTITY_SUMMARY_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content or ""
        raw = _clean_llm_output(raw)
        logger.info("Generated summary for entity %s: %s", entity_name, raw[:100])
        return raw.strip() if raw.strip() else f"{entity_name} ({entity_type})"
    except Exception:
        logger.exception("Entity summary generation failed for %s", entity_name)
        # Fallback: simple concatenation
        return f"{entity_name} ({entity_type}): " + "; ".join(facts[:10])


def extract_triplets(content: str, context: str = "", goal: str = "", language: str = "zh") -> list[Triplet]:
    """Call LLM to extract entity-relation triplets from text.

    Args:
        content: The text to extract from.
        context: Optional previous context for pronoun resolution.
        goal: Optional analytical goal for directed extraction (推演目标).
    """
    # 快速过滤：如果内容太短或只是垃圾数据，直接返回空
    content_stripped = content.strip()

    # 1. 太短的内容
    if len(content_stripped) < 10:
        logger.info("Content too short (%d chars), skipping extraction", len(content_stripped))
        return []

    # 2. 纯数字、纯符号、重复字符
    import re
    # 纯数字（如 123, 222, 12345）
    if re.fullmatch(r'\d+', content_stripped):
        logger.info("Content is pure numbers, skipping extraction")
        return []

    # 重复单个字符（如 aaa, 111, !!!, ...）
    if re.fullmatch(r'(.)\1+', content_stripped):
        logger.info("Content is repeated character, skipping extraction")
        return []

    # 纯符号（如 !!!, ???, ...）
    if re.fullmatch(r'[^\w\s]+', content_stripped, re.UNICODE):
        logger.info("Content is pure symbols, skipping extraction")
        return []

    # 纯空格/换行
    if not content_stripped or content_stripped.isspace():
        logger.info("Content is empty or whitespace, skipping extraction")
        return []

    # 3. 简单的问候语、口语词汇
    meaningless_words = {
        # 中文
        "你好", "您好", "嗨", "哈喽", "谢谢", "好的", "是的", "不是", "嗯", "哦", "啊",
        "呃", "额", "哈哈", "呵呵", "嘿嘿", "嘻嘻", "ok", "okay", "嗯嗯", "好",
        # 英文
        "hi", "hello", "hey", "thanks", "thank you", "yes", "no", "ok", "okay",
        "yeah", "yep", "nope", "haha", "lol", "hehe",
        # 数字词
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
        "11", "22", "33", "44", "55", "66", "77", "88", "99",
        "111", "222", "333", "444", "555", "666", "777", "888", "999",
    }
    if content_stripped.lower() in meaningless_words:
        logger.info("Content is meaningless word, skipping extraction")
        return []

    # 4. 计算有效字符比例（排除数字、符号）
    alpha_chars = re.findall(r'[\w]', content_stripped, re.UNICODE)
    digit_chars = re.findall(r'\d', content_stripped)

    # 如果数字占比超过80%，认为是无效内容
    if len(alpha_chars) > 0 and len(digit_chars) / len(alpha_chars) > 0.8:
        logger.info("Content is mostly digits (%.1f%%), skipping extraction",
                   len(digit_chars) / len(alpha_chars) * 100)
        return []

    logger.info(f"开始提取三元组，内容长度: {len(content)} 字符")

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    # Build system prompt: inject language and goal
    language_name = "Chinese (中文)" if language == "zh" else "English"

    # Simplified prompt (inspired by MiroFish)
    system_prompt = f"""你是知识图谱提取专家。从文本中提取实体和关系。

返回JSON格式:
{{
  "entities": [
    {{"name": "实体名", "type": "实体类型", "summary": "实体描述"}}
  ],
  "relations": [
    {{"source": "源实体", "target": "目标实体", "type": "关系类型", "fact": "关系描述"}}
  ]
}}

要求:
1. 只提取文本中明确提到的实体和关系
2. 实体 type 用英文 snake_case (person, organization, country, location, concept, event, product, technology 等)
3. 实体 summary 应简洁描述实体（不超过50字）
4. 关系 fact 应描述关系具体内容（不超过100字）
5. 返回有效的 JSON，无其他内容
"""

    if goal:
        system_prompt += f"\n\n分析目标: {goal}\n优先提取与此目标相关的实体和关系。"

    # Simplified: 不使用复杂的上下文标注，直接传递内容
    user_message = content

    try:
        import time
        start_time = time.time()

        # 增加超时时间到 90 秒，并添加重试逻辑
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # 尝试使用 JSON mode（参考 MiroFish）
                logger.info(f"调用 LLM API (尝试 {attempt + 1}/{max_retries}), 模型: {settings.llm_model_name}, 超时: 90s")
                response = client.chat.completions.create(
                    model=settings.llm_model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.0,
                    timeout=90.0,
                    response_format={"type": "json_object"}  # 强制返回 JSON
                )
                logger.info("LLM API 调用成功")
                break  # 成功，跳出重试循环
            except Exception as e:
                # JSON mode 可能不支持，降级到普通模式
                if "response_format" in str(e).lower() or "json_object" in str(e).lower():
                    logger.warning("JSON mode not supported, fallback to normal mode")
                    try:
                        response = client.chat.completions.create(
                            model=settings.llm_model_name,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message},
                            ],
                            temperature=0.0,
                            timeout=90.0
                        )
                        break
                    except Exception as e2:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 5
                            logger.warning(f"LLM request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e2}")
                            time.sleep(wait_time)
                        else:
                            raise
                elif attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"LLM request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise

        elapsed = time.time() - start_time
        logger.info(f"LLM extraction took {elapsed:.1f}s for {len(content)} chars")

        raw = response.choices[0].message.content or ""
        raw = _clean_llm_output(raw)

        # Multi-level JSON parsing with repair strategy
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON parse failed: {e}, trying repair strategies")
            # Try repair strategies
            try:
                fixed_json = _fix_json_string(raw)
                data = json.loads(fixed_json)
                logger.info("JSON repaired successfully")
            except json.JSONDecodeError as e2:
                logger.error(f"JSON repair failed. Original error at char {e.pos}: {raw[max(0, e.pos-50):e.pos+50]}")
                logger.error(f"Full response: {raw[:500]}")
                raise ValueError(f"Invalid JSON from LLM (char {e.pos}): {str(e)}") from e2

        # Parse new format: {"entities": [...], "relations": [...]}
        entities = []
        relations = []

        if isinstance(data, dict):
            entities = data.get("entities", [])
            relations = data.get("relations", [])
        elif isinstance(data, list):
            # Fallback: old format with triplets array
            logger.warning("LLM returned old triplet format, converting to new format")
            relations = data
            # Extract unique entities from relations
            entity_map = {}
            for item in data:
                subj = item.get("subject", "")
                subj_type = item.get("subject_type", "")
                if subj and subj not in entity_map:
                    entity_map[subj] = {"name": subj, "type": subj_type, "summary": ""}

                obj = item.get("object", "")
                obj_type = item.get("object_type", "")
                if obj and obj not in entity_map:
                    entity_map[obj] = {"name": obj, "type": obj_type, "summary": ""}
            entities = list(entity_map.values())

        if not isinstance(entities, list) or not isinstance(relations, list):
            logger.warning("LLM returned malformed JSON: %s", raw[:200])
            return []

        # Build entity summary map: name -> summary
        entity_summaries = {}
        for e in entities:
            name = str(e.get("name", "")).strip()
            summary = str(e.get("summary", "")).strip()
            if name:
                entity_summaries[name] = summary

        # Build triplets from relations
        triplets = []
        for item in relations:
            try:
                source = str(item.get("source", "")).strip()
                target = str(item.get("target", "")).strip()
                rel_type = str(item.get("type", "")).strip()
                fact = str(item.get("fact", "")).strip()

                if not (source and target and rel_type):
                    continue

                # 放宽验证：允许 LLM 使用规范化实体名或代词解析后的名称
                # MiroFish 不做这个验证，我们也移除以提高召回率

                # Get entity types from entities array
                source_type = "concept"
                target_type = "concept"
                for e in entities:
                    if e.get("name") == source:
                        source_type = e.get("type", "concept")
                    if e.get("name") == target:
                        target_type = e.get("type", "concept")

                triplets.append(
                    Triplet(
                        subject=source,
                        subject_type=_normalize_entity_type(source_type),
                        predicate=rel_type.strip().lower(),
                        object=target,
                        object_type=_normalize_entity_type(target_type),
                        fact=fact,
                        subject_summary=entity_summaries.get(source, ""),
                        object_summary=entity_summaries.get(target, ""),
                        confidence=1.0,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.warning("Skipping malformed relation %s: %s", item, e)
                continue

        logger.info("Extracted %d entities, %d relations from text (%d chars), %d triplets after filtering",
                   len(entities), len(relations), len(content), len(triplets))
        return triplets

    except Exception:
        logger.exception("Triplet extraction failed")
        return []
