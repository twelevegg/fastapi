from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.marketing.state import MarketingState
from app.agent.marketing.nodes import analyze_node, retrieve_node, generate_node

def is_marketing_needed(state: MarketingState):
    """Conditional Edge Logic"""
    if state.get("marketing_needed"):
        return "retrieve"
    return "generate" # Or skip retrieval and just chitchat?

def build_marketing_graph():
    workflow = StateGraph(MarketingState)

    workflow.add_node("analyze", analyze_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)

    workflow.set_entry_point("analyze")
    
    # [Optimization] Conditional Edge: Skip Retrieve if not needed
    workflow.add_conditional_edges(
        "analyze",
        is_marketing_needed,
        {
            "retrieve": "retrieve",
            "generate": "generate"
        }
    )
    # workflow.add_edge("analyze", "retrieve") 
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile(checkpointer=MemorySaver())
