from __future__ import annotations

import json
from typing import Optional

from app.services.openai_service import openai_service
from app.schemas.qa import MemoryModel, OverallQAResult, GrowthPoint, SentenceHighlight
from .prompts import GROWTH_POINT_PROMPT
from .utils import safe_json_loads


async def build_growth_points(
    overall: OverallQAResult,
    top_sentences: list[SentenceHighlight],
    bottom_sentences: list[SentenceHighlight],
    memory: Optional[MemoryModel],
    model: str = "gpt-4o-mini",
) -> list[GrowthPoint]:
    memory_text = ""
    if memory is not None:
        memory_text = json.dumps(memory.model_dump(), ensure_ascii=False)

    top_block = "\n".join(
        [
            f"- (점수 {t.sentence_score}) 상담사: {t.agent_utterance}\n  피드백: {t.short_feedback}"
            for t in top_sentences
        ]
    )
    bottom_block = "\n".join(
        [
            f"- (점수 {b.sentence_score}) 상담사: {b.agent_utterance}\n  피드백: {b.short_feedback}\n  모범: {b.expert_recommended_response}"
            for b in bottom_sentences
        ]
    )

    prompt = GROWTH_POINT_PROMPT.format(
        memory_text=memory_text,
        overall_json=overall.model_dump_json(ensure_ascii=False),
        top_block=top_block,
        bottom_block=bottom_block,
    )

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": prompt}],
        model=model,
        max_tokens=450,
        temperature=0.2,
    )
    data = safe_json_loads(text)

    return [GrowthPoint.model_validate(x) for x in data.get("growth_points", [])]
