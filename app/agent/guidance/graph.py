from langgraph.graph import StateGraph, END
from app.agent.guidance.state import AgentState
from app.agent.guidance.nodes import analyze_messages_node, retrieval_node, generate_node

# conditional edge
async def decide_rag(state: AgentState):
  """ 상담 내역 분석 후 Agent가 어떤 행동을 할지 라우팅하는 함수
  1. 분석 결과 "retrieve": RAG 활용해 추천 답변과 다음 행동 제시
  2. 분석 결과 "generate": RAG 스킵하고 추천 답변과 다음 행동 제시
  3. 분석 결과 "skip": 해당 워크플로우 즉시 종료
  """

  if state["next_step"] == "retrieve":
    return "retrieve"
  elif state["next_step"] == "generate":
    return "generate"
  else:
    return "skip"

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze", analyze_messages_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("generate", generate_node)

    workflow.set_entry_point("analyze")
    workflow.add_conditional_edges("analyze", decide_rag,
                                {
                                    "retrieve": "retrieve",
                                    "generate": "generate",
                                    "skip": END
                                })
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()