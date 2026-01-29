from langgraph.graph import StateGraph, END
from .state import AgentState
from nodes import (
    node_initialize,
    node_curriculum_manager,
    node_content_creator,
    node_quiz_generator,
    node_grader
)

def node_human_input(state: AgentState):
    print(f"\n" + "="*60)
    print(f"🎬 교육 영상 생성 완료: {state.get('current_video_path')}")
    print("📺 영상을 시청하신 후, 아래 퀴즈의 정답을 입력해 주세요!")
    print("="*60)
    
    user_answers = []
    quiz_list = state['current_quiz']
    
    for i, q in enumerate(quiz_list):
        while True:  # 유효한 입력을 받을 때까지 무한 루프
            print(f"\n[문제 {i+1}/{len(quiz_list)}] {q['question']}")
            for idx, option in enumerate(q['options']):
                print(f"   {idx}. {option}")
            
            user_input = input("\n➤ 정답 번호를 입력하세요 (0~3): ").strip()
            
            # 숫자이고 0~3 사이인지 검증
            if user_input.isdigit() and 0 <= int(user_input) <= 3:
                user_answers.append(int(user_input))
                break
            else:
                print("❌ 잘못된 입력입니다. 0, 1, 2, 3 중 하나의 숫자만 입력해 주세요.")
                
    print(f"\n✅ 모든 답변이 제출되었습니다. 채점을 시작합니다...")
    return {"user_answers": user_answers}

def route_after_grader(state: AgentState):
    if not state['unlearned_ids'] and not state['weak_ids']:
        return "end" # 모든 학습 완료 및 복습 완료
    return "curriculum" # 계속 학습

def create_graph():
    workflow = StateGraph(AgentState)
    
    # 노드 추가
    workflow.add_node("init", node_initialize)
    workflow.add_node("curriculum", node_curriculum_manager)
    workflow.add_node("content_gen", node_content_creator)
    workflow.add_node("quiz_gen", node_quiz_generator)
    workflow.add_node("human_input", node_human_input)
    workflow.add_node("grader", node_grader)
    
    # 엣지 연결
    workflow.set_entry_point("init")
    workflow.add_edge("init", "curriculum")
    
    # 조건부 엣지: 커리큘럼에서 더 할게 없으면 종료
    def check_complete(state):
        if state.get("is_complete"):
            return "end"
        return "content_gen"
        
    workflow.add_conditional_edges(
        "curriculum",
        check_complete,
        {
            "content_gen": "content_gen",
            "end": END
        }
    )
    
    workflow.add_edge("content_gen", "quiz_gen")
    workflow.add_edge("quiz_gen", "human_input")
    workflow.add_edge("human_input", "grader")
    
    # 채점 후 다시 커리큘럼으로 (틀린건 weak_ids에 들어가 있으므로 커리큘럼이 알아서 처리)
    workflow.add_edge("grader", "curriculum")
    
    return workflow.compile()