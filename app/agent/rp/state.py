from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages


class Memory(TypedDict, total=False):
    claimed_issue: str
    explained_causes: list[dict]
    accepted_causes: list[dict]
    rejected_causes: list[dict]
    customer_understanding: str
    customer_acceptance: bool


class RPState(TypedDict):
    messages: Annotated[list, add_messages]

    persona: dict | None

    start_call: bool | None

    # 시스템 상태
    current_goal: str
    understanding_level: int
    ready_to_close: bool

    # ✅ 기억 전용 영역 (핵심)
    memory: Memory | None

    # 내부 처리용 (임시)
    memory_candidate: dict | None
