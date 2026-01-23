from app.agent.rp.graph import build_graph

# ✅ 앱 시작 시 그래프 1회 생성
graph = build_graph()


async def handle_agent_message(session_id: str, message: str):
    """
    LangGraph가 state를 전부 관리한다.
    우리는:
    - user 메시지만 전달
    - session_id를 thread_id로 매핑
    """
    result = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ]
        },
        config={
            "configurable": {
                "thread_id": session_id  # 🔥 핵심
            }
        }
    )

    return result
