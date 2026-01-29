# app/agent/rp/graph.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.rp.state import RPState as State
from app.agent.rp.nodes import (
    init_state_node,
    state_update_node,
    customer_talk_node,
    close_talk_node,
    decide_mode,
    # ✅ memory 관련 노드 (nodes.py에 있어야 함)
    memory_extraction_node,
    memory_apply_node,  # ✅ 이 노드는 nodes.py에 추가 필요
)

# ✅ in-memory 체크포인터 (프로세스 살아있는 동안 세션 유지)
memory = MemorySaver()


def build_graph():
    workflow = StateGraph(State)

    # -----------------------
    # Nodes
    # -----------------------
    workflow.add_node("init_state", init_state_node)
    workflow.add_node("state_update", state_update_node)

    workflow.add_node("customer_talk", customer_talk_node)
    workflow.add_node("close_talk", close_talk_node)

    workflow.add_node("memory_extraction", memory_extraction_node)
    workflow.add_node("memory_apply", memory_apply_node)

    # -----------------------
    # Edges
    # -----------------------
    workflow.add_edge(START, "init_state")
    workflow.add_edge("init_state", "state_update")

    # state_update -> (talk|close)
    workflow.add_conditional_edges(
        "state_update",
        decide_mode,
        {
            "talk": "customer_talk",
            "close": "close_talk",
        },
    )

    # talk 후: memory 업데이트 파이프라인
    workflow.add_edge("customer_talk", "memory_extraction")
    workflow.add_edge("memory_extraction", "memory_apply")
    workflow.add_edge("memory_apply", END)

    # close 흐름: 종료 멘트 -> QA 평가 -> 종료
    workflow.add_edge("close_talk", END)

    # ✅ 핵심: checkpointer 붙이기 (thread_id로 세션 유지)
    return workflow.compile(checkpointer=memory)
