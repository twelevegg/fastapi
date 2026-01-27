from __future__ import annotations

import asyncio
from typing import Optional

from app.schemas.qa import (
    QAReportRequest,
    QAReportResponse,
    SentenceHighlight,
    TurnEvaluation,
)
from app.agent.qa import (
    pick_representative_agent_turns,
    evaluate_overall,
    evaluate_turn,
    build_growth_points,
    calc_sentence_score,
)


class QAService:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def _build_top_bottom(
        self,
        turns: list[TurnEvaluation],
        top_k: int = 3,
        bottom_k: int = 3,
    ) -> tuple[list[SentenceHighlight], list[SentenceHighlight]]:
        if not turns:
            return [], []

        desc = sorted(turns, key=lambda x: x.sentence_score, reverse=True)
        asc = sorted(turns, key=lambda x: x.sentence_score)

        def to_h(t: TurnEvaluation) -> SentenceHighlight:
            return SentenceHighlight(
                turn_index=t.turn_index,
                customer_utterance=t.customer_utterance,
                agent_utterance=t.agent_utterance,
                expert_recommended_response=t.expert_recommended_response,
                sentence_score=t.sentence_score,
            )

        top = [to_h(t) for t in desc[:top_k]]
        bottom = [to_h(t) for t in asc[:bottom_k]]
        return top, bottom

    async def build_report(self, req: QAReportRequest) -> QAReportResponse:
        messages = [m.model_dump() for m in req.messages]

        # 1) 전체 맥락 기반 종합 평가 (항상 전체 대화)
        overall = await evaluate_overall(messages, req.memory, model=self.model)

        # 2) 대표 문장 인덱스 선별 (오프닝/마무리 포함 + 키워드/균등)
        rep_indices = pick_representative_agent_turns(
            messages=messages,
            max_turn_evals=req.max_turn_evals,
            use_keyword_pick=req.use_keyword_pick,
        )

        # 3) 대표 문장들에 대해 문장별 QA 수행 (동시 제한)
        sem = asyncio.Semaphore(3)

        async def _eval_one(idx: int):
            async with sem:
                # 문장 점수(가중치 합) 계산은 여기서 먼저 해도 되고,
                # turn_level 결과(scores) 기반으로 다시 계산해도 됨.
                # 여기서는 "scores 나오고 나서 계산"이 더 정확하니,
                # turn_level에 sentence_score를 넣기 위해 임시로 3.0 넣고,
                # 결과 받은 뒤 계산해서 재할당한다.
                tmp_score = 3.0
                te = await evaluate_turn(
                    messages=messages,
                    turn_index=idx,
                    memory=req.memory,
                    sentence_score=tmp_score,
                    model=self.model,
                )
                te.sentence_score = calc_sentence_score(
                    accuracy=int(te.scores.accuracy),
                    clarity=int(te.scores.clarity),
                    empathy=int(te.scores.empathy),
                    w_accuracy=req.w_accuracy,
                    w_clarity=req.w_clarity,
                    w_empathy=req.w_empathy,
                )
                return te

        turns = await asyncio.gather(*[_eval_one(i) for i in rep_indices])
        turns = sorted(turns, key=lambda x: x.turn_index)

        # 4) TOP3 / BOTTOM3
        top, bottom = self._build_top_bottom(turns, top_k=3, bottom_k=3)

        # 5) 성장포인트 1~2개
        growth_points = await build_growth_points(
            overall=overall,
            top_sentences=top,
            bottom_sentences=bottom,
            memory=req.memory,
            model=self.model,
        )

        return QAReportResponse(
            session_id=req.session_id,
            overall=overall,
            turns=turns,
            top_sentences=top,
            bottom_sentences=bottom,
            growth_points=growth_points,
        )


qa_service = QAService(model="gpt-4o-mini")