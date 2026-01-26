from typing_extensions import TypedDict
from typing import Annotated, Optional, List, Literal
from langchain_core.messages import BaseMessage, add_messages

class AgentState(TypedDict):
  message: Annotated[List[BaseMessage], add_messages] # 상담 텍스트
  context: Optional[str] # Qdrant에서 검색된 관련 자료들
  customer_info: Optional[dict] # 고객 정보
  resoning: Optional[str] # AI가 선택한 다음 행동의 근거
  next_step: Literal["retrieve", "generate", "skip"]
  search_filter: List[Literal["guideline", "terms"]] # Qdrant 검색 필터
  search_query: Optional[str] # Qdrant 검색 쿼리
  recommended_answer: Optional[str]
  work_guide: Optional[str]


class AnalysisOutput(TypedDict):
  resoning: str
  next_step: Literal["retrieve", "generate", "skip"]
  search_filter: List[Literal["guideline", "terms"]]


class GenerateOutput(TypedDict):
  recommended_answer: str
  work_guide: str

