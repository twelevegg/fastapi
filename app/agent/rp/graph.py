from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.rp.state import RPState as State
from app.agent.rp.nodes import (
    init_state_node,
    state_update_node,
    customer_talk_node,
    close_talk_node,
    summarize_node,
    qa_evaluate_node,
    decide_mode,
    should_summarize,
)

# ✅ MemorySaver 생성
memory = MemorySaver()


def build_graph():
    workflow = StateGraph(State)

    workflow.add_node("init_state", init_state_node)
    workflow.add_node("state_update", state_update_node)
    workflow.add_node("customer_talk", customer_talk_node)
    workflow.add_node("close_talk", close_talk_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("qa_evaluate", qa_evaluate_node)

    workflow.add_edge(START, "init_state")
    workflow.add_edge("init_state", "state_update")
    workflow.add_conditional_edges(
        "state_update",
        decide_mode,
        {
            "talk": "customer_talk",
            "close": "close_talk",
        }
    )

    workflow.add_conditional_edges(
        "customer_talk",
        should_summarize,
        {
            "summarize": "summarize",
            "skip": END,
        }
    )

    workflow.add_edge("summarize", END)
    workflow.add_edge("close_talk", "qa_evaluate")
    workflow.add_edge("qa_evaluate", END)

    # ✅ 핵심: checkpointer 붙이기
    return workflow.compile(checkpointer=memory)