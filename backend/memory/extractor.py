"""LLM-based entity/relation triplet extraction from text."""

import json
import logging
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def _clean_llm_output(text: str) -> str:
    """Remove <think> blocks and markdown code fences from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?\s*\n?", "", text)
    return text.strip()

EXTRACTION_PROMPT = """\
You are a knowledge graph extraction engine. Given a piece of conversation text, \
extract factual triplets (subject, predicate, object).

Rules:
1. Extract ONLY concrete, factual information — not opinions or speculation.
2. Each triplet must have: subject, subject_type, predicate, object, object_type, fact.
3. "fact" is a short natural-language sentence summarizing the triplet.
4. subject_type and object_type should be one of: person, organization, location, concept, event, product, skill, time.
5. If no factual triplets can be extracted, return an empty array.
6. Return ONLY a JSON array, no other text.
7. IMPORTANT: Resolve all pronouns (I/me/我/他/她) to specific entity names using the context provided. \
Never use "说话者", "用户", "speaker" as a subject — always resolve to the actual person's name.

Example output:
[
  {
    "subject": "张三",
    "subject_type": "person",
    "predicate": "works_at",
    "object": "百度",
    "object_type": "organization",
    "fact": "张三在百度工作"
  }
]
"""


@dataclass
class Triplet:
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str
    fact: str


def extract_triplets(content: str, context: str = "") -> list[Triplet]:
    """Call MiniMax LLM to extract entity-relation triplets from text."""
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    user_message = content
    if context:
        user_message = f"[Previous context for reference]\n{context}\n\n[Current text to extract from]\n{content}"

    try:
        response = client.chat.completions.create(
            model=settings.llm_model_name,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
        )

        raw = response.choices[0].message.content or ""
        raw = _clean_llm_output(raw)
        data = json.loads(raw)

        # Handle both {"triplets": [...]} and [...] formats
        if isinstance(data, dict):
            data = data.get("triplets", data.get("results", []))
        if not isinstance(data, list):
            logger.warning("LLM returned non-list JSON: %s", raw[:200])
            return []

        triplets = []
        for item in data:
            try:
                triplets.append(
                    Triplet(
                        subject=str(item["subject"]).strip(),
                        subject_type=str(item["subject_type"]).strip().lower(),
                        predicate=str(item["predicate"]).strip().lower(),
                        object=str(item["object"]).strip(),
                        object_type=str(item["object_type"]).strip().lower(),
                        fact=str(item["fact"]).strip(),
                    )
                )
            except (KeyError, TypeError) as e:
                logger.warning("Skipping malformed triplet %s: %s", item, e)
                continue

        logger.info("Extracted %d triplets from text (%d chars)", len(triplets), len(content))
        return triplets

    except Exception:
        logger.exception("Triplet extraction failed")
        return []
