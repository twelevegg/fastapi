from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from app.agent.guidance.graph import build_graph

# 그래프 초기화 (서버 시작 시 1회)
graph = build_graph()

async def handle_guidance_message(turn: dict, session_id: str, customer_info: dict = None):
    """
    Guidance Agent 그래프를 실행하거나 받아온 메시지로 상태를 업데이트합니다.
    Args:
        turn: 단일 턴 데이터 {"speaker": "...", "transcript": "...", "turn_id": ...}
        session_id: 대화 세션 ID (thread_id로 사용)
        customer_info: 고객 정보 (첫 턴에만 전달됨)
    """
    speaker = turn.get("speaker")
    transcript = turn.get("transcript", "")
    turn_id = turn.get("turn_id")
    
    # 메타데이터 구성
    extra_data = {}
    if turn_id is not None:
        extra_data["turn_id"] = turn_id

    # 메시지 객체 생성
    message_obj = None
    if speaker == "customer":
        message_obj = HumanMessage(content=transcript, additional_kwargs=extra_data)
    else:
        # 상담사(agent/counselor) 발화는 AIMessage로 취급
        # name='counselor'를 주어 analysis 노드에서 식별 가능하게 함
        message_obj = AIMessage(content=transcript, name="counselor", additional_kwargs=extra_data)

    # LangGraph Config
    config = {"configurable": {"thread_id": session_id}}

    # 로직 분기
    if speaker == "agent":
        # 상담사 발화는 분석하지 않고 State에만 적재 (비용/속도 효율)
        state_update = {"message": [message_obj]}
        if customer_info:
             state_update["customer_info"] = customer_info
             
        graph.update_state(config, state_update)
        
        # [DEBUG] 메시지 적재되는지 확인
        current_state = graph.get_state(config)
        print(f"\n[Guidance] Current Messages (Thread {session_id}):")
        if current_state and current_state.values:
            for msg in current_state.values.get("message", []):
                print(f" - [{msg.type}] {msg.content}")
        # 디버깅용이라 나중에 삭제할 것===============================================

        return {
            "next_step": "skip",
            "reasoning": "counselor turn accumulated",
            "recommended_answer": None,
            "work_guide": None
        }
    else:
        # 고객 발화는 그래프 실행 (분석 -> RAG -> 생성)
        inputs = {"message": [message_obj]}
        if customer_info:
            inputs["customer_info"] = customer_info
            
        result = await graph.ainvoke(inputs, config=config)
        
        # [DEBUG] 메시지 적재 확인
        current_state = graph.get_state(config)
        print(f"\n[Guidance] Current Messages (Thread {session_id}):")
        if current_state and current_state.values:
            for msg in current_state.values.get("message", []):
                print(f" - [{msg.type}] {msg.content}")
        
        # HumanMessage 등은 JSON 직렬화가 안되므로 필요한 값만 추출하여 반환
        return {
            "agent_type": "guidance",
            "next_step": result.get("next_step"),
            "recommended_answer": result.get("recommended_answer"),
            "work_guide": result.get("work_guide"),
            "reasoning": result.get("reasoning"),
        }