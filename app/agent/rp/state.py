from typing import TypedDict, List, Optional

class RPState(TypedDict):
    messages: List[dict]
    summary: Optional[str]
    current_goal: str
    understanding_level: int
    ready_to_close: bool
    qa_result: Optional[dict]