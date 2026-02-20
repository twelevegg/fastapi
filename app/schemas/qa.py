# app/schemas/qa.py
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------- Input ----------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # user=상담사, assistant=고객(RP)
    content: str


class MemoryModel(BaseModel):
    claimed_issue: Optional[str] = None
    explained_causes: list[dict[str, Any]] = Field(default_factory=list)
    accepted_causes: list[dict[str, Any]] = Field(default_factory=list)
    rejected_causes: list[dict[str, Any]] = Field(default_factory=list)
    customer_understanding: Optional[str] = None
    customer_acceptance: Optional[bool] = None


class QAReportRequest(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    memory: Optional[MemoryModel] = None

    # 대표 문장 평가 최대 개수(0이면 상담사 발화 전체 평가)
    max_turn_evals: int = 10

    # 문장 점수 가중치(TOP/BOTTOM 선정)
    w_accuracy: float = 0.4
    w_clarity: float = 0.3
    w_empathy: float = 0.3

    # 대표문장 선별: 키워드 기반 후보 포함 여부
    use_keyword_pick: bool = True


# ---------- Overall QA ----------
class OverallCategoryScores(BaseModel):
    problem_understanding: int = Field(ge=0, le=5)
    explanation_clarity: int = Field(ge=0, le=5)
    tone_and_attitude: int = Field(ge=0, le=5)
    flow_control: int = Field(ge=0, le=5)
    closing: int = Field(ge=0, le=5)


class OverallQAResult(BaseModel):
    overall_score: int = Field(ge=0, le=5)
    category_scores: OverallCategoryScores
    strengths: list[str]
    weaknesses: list[str]
    one_line_feedback: str


# ---------- Turn-level QA ----------
class TurnScores(BaseModel):
    accuracy: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    empathy: int = Field(ge=1, le=5)


class TurnEvaluation(BaseModel):
    turn_index: int  # messages index (상담사 발화 위치)
    customer_utterance: str
    agent_utterance: str

    expert_recommended_response: str
    scores: TurnScores
    positive_feedback: str | None = None
    negative_feedback: str | None = None

    # 가중치 합산 점수 (TOP/BOTTOM 선별)
    sentence_score: float = Field(ge=1.0, le=5.0)


class SentenceHighlight(BaseModel):
    turn_index: int
    customer_utterance: str
    agent_utterance: str
    expert_recommended_response: str
    sentence_score: float
    short_feedback: str | None = None
    positive_feedback: str | None = None
    negative_feedback: str | None = None


# ---------- Growth Points ----------
class GrowthPoint(BaseModel):
    focus: str
    when: str
    why: str
    how: str
    example_sentence: str


# ---------- Response ----------
class QAReportResponse(BaseModel):
    session_id: str

    overall: OverallQAResult
    # 대표 문장들(선별된 문장)의 평가 결과
    turns: list[TurnEvaluation]

    # UI용 하이라이트
    top_sentences: list[SentenceHighlight]
    bottom_sentences: list[SentenceHighlight]

    # 다음 연습 목표
    growth_points: list[GrowthPoint]
