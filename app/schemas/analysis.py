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
    member_id: Optional[int] = Field(None, description="상담원 ID (로그인된 사용자)")
    tenant_name: Optional[str] = Field(None, description="테넌트 이름 (예: default)")
    
    # [NEW] 통화 시간 관련 메트릭
    start_time: Optional[str] = Field(None, description="통화 시작 시간 (ISO 8601)")
    end_time: Optional[str] = Field(None, description="통화 종료 시간 (ISO 8601)")
    duration: Optional[int] = Field(None, description="총 통화 기간(초)")
    billsec: Optional[int] = Field(None, description="실제 과금/발화 기간(초)")

    transcripts: List[dict] = Field(..., description="상담 전문 (Speaker, Transcript)")

