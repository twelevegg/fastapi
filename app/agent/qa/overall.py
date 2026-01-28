from __future__ import annotations

import json
from typing import Optional

from app.services.openai_service import openai_service
from app.schemas.qa import OverallQAResult, MemoryModel
from .prompts import OVERALL_QA_PROMPT
from .utils import safe_json_loads, build_convo_text


async def evaluate_overall(
    messages: list[dict[str, str]],
    memory: Optional[MemoryModel],
    model: str = "gpt-4o-mini",
) -> OverallQAResult:
    convo = build_convo_text(messages)
    memory_text = ""
    if memory is not None:
        memory_text = json.dumps(memory.model_dump(), ensure_ascii=False)

    prompt = OVERALL_QA_PROMPT.format(memory_text=memory_text, convo=convo)

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": prompt}],
        model=model,
        max_tokens=550,
        temperature=0.2,
    )
    data = safe_json_loads(text)
    return OverallQAResult.model_validate(data)
