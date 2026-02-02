from pydantic import BaseModel, Field
from typing import List, Optional

class CallAnalysisResult(BaseModel):
    summary_text: str = Field(description="상담 내용을 요약한 텍스트")
    estimated_cost: int = Field(description="상담 내용에 기반한 추정 비용 (원 단위)")
    ces_score: float = Field(description="고객 노력 점수 (0-10), 낮을수록 좋음 (고객이 문제를 해결하기 쉬웠는지)")
    csat_score: float = Field(description="고객 만족도 (0-100), 높을수록 좋음")
    rps_score: float = Field(description="순수 추천 고객 지수 (0-10), 높을수록 좋음")
    keyword: List[str] = Field(description="상담의 핵심 키워드 리스트")
    violence_count: int = Field(description="상담 중 고객의 폭언/욕설 횟수")

class CallLogPayload(CallAnalysisResult):
    """Spring 서버로 전송할 최종 데이터 스키마"""
    customer_number: Optional[str] = Field(None, description="고객 전화번호")
    transcripts: List[dict] = Field(..., description="상담 전문 (Speaker, Transcript)")

