from typing import List, TypedDict, Optional

class KnowledgeUnit(TypedDict):
    id: str
    content: str
    source: str
    page: Optional[int]
    is_learned: bool

class QuizItem(TypedDict):
    question: str
    options: List[str]
    correct_answer: int  # 0-3 index
    explanation_ref: str # RAG context

class AgentState(TypedDict):
    # 전체 데이터
    knowledge_base: List[KnowledgeUnit] # 전체 학습 청크
    
    # 학습 큐 관리
    unlearned_ids: List[str] # 아직 안 배운 ID
    weak_ids: List[str]      # 틀려서 복습 필요한 ID
    mastered_ids: List[str]  # 통과한 ID
    
    # 현재 세션 데이터
    current_batch_ids: List[str] # 이번 영상에 포함될 ID들
    current_script: str
    current_image_paths: List[str]
    current_audio_path: str
    current_video_path: str
    # PPT는 더 이상 생성하지 않음 (영상만 생성)
    current_ppt_path: Optional[str]
    
    # 평가 데이터
    current_quiz: List[QuizItem]
    user_answers: List[int]
    quiz_score: int
    quiz_feedback: str
    
    # 종료 플래그
    is_complete: bool