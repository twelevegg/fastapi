from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field

class JobCreateResponse(BaseModel):
    job_id: str
    status: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: Optional[str] = None
    progress: int = 0
    round_index: int = 0
    is_complete: bool = False
    video_ready: bool = False
    quiz_ready: bool = False
    video_url: Optional[str] = None
    quiz: Optional[list] = None
    last_score: Optional[float] = None

class GradeRequest(BaseModel):
    user_answers: List[int] = Field(default_factory=list)

class GradeResponse(BaseModel):
    job_id: str
    score: float
    is_complete: bool
    feedback: str
    # optionally include updated buckets
    mastered: int | None = None
    weak: int | None = None
    unlearned: int | None = None

class NextRoundResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
