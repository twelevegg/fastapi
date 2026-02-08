from typing import Any, cast
from app.agent.rp.graph import build_graph
from app.agent.rp.state import RPState

# ✅ 앱 시작 시 그래프 1회 생성
graph = build_graph()


async def handle_agent_message(
    session_id: str, message: str, persona: dict | None = None, start: bool = False
):
    """
    LangGraph가 state를 전부 관리한다.
    우리는:
    - user 메시지만 전달
    - session_id를 thread_id로 매핑
    """
    payload: dict[str, Any] = {"messages": [{"role": "user", "content": message}]}

    if persona is not None:
        payload["persona"] = persona

    if start:
        payload["start_call"] = True

    result = await graph.ainvoke(
        cast(RPState, payload),
        config={
            "configurable": {
                "thread_id": session_id  # 🔥 핵심
            }
        },
    )

    return result
