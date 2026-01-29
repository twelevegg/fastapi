from __future__ import annotations

import json
from typing import Optional

from app.services.openai_service import openai_service
from app.schemas.qa import MemoryModel, TurnEvaluation
from .prompts import TURN_LEVEL_QA_PROMPT
from .utils import safe_json_loads


def _find_prev_customer_utterance(messages: list[dict[str, str]], turn_index: int) -> str:
    for i in range(turn_index - 1, -1, -1):
        if messages[i]["role"] == "assistant":
            return messages[i]["content"]
    return ""


async def evaluate_turn(
    messages: list[dict[str, str]],
    turn_index: int,
    memory: Optional[MemoryModel],
    *,
    sentence_score: float,
    model: str = "gpt-4o-mini",
) -> TurnEvaluation:
    agent_utterance = messages[turn_index]["content"]
    customer_utterance = _find_prev_customer_utterance(messages, turn_index)

    memory_text = ""
    if memory is not None:
        memory_text = json.dumps(memory.model_dump(), ensure_ascii=False)

    prompt = TURN_LEVEL_QA_PROMPT.format(
        customer_utterance=customer_utterance,
        agent_utterance=agent_utterance,
        memory_text=memory_text,
    )

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": prompt}],
        model=model,
        max_tokens=380,
        temperature=0.2,
    )
    data = safe_json_loads(text)

    # TurnEvaluation 스키마에 맞춰 구성
    return TurnEvaluation(
        turn_index=turn_index,
        customer_utterance=customer_utterance,
        agent_utterance=agent_utterance,
        expert_recommended_response=data["expert_recommended_response"],
        scores=data["scores"],
        positive_feedback=data.get("positive_feedback"),
        negative_feedback=data.get("negative_feedback"),
        sentence_score=sentence_score,
    )
