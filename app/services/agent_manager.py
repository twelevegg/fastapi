import asyncio
from typing import List, Callable, Any, Dict

class AgentManager:
    def __init__(self):
        self.agents: List[Callable] = []

    def register_agent(self, agent_handler: Callable):
        """
        에이전트 처리 함수를 등록합니다.
        해당 함수는 (turn: dict, session_id: str, **kwargs) 시그니처를 가져야 합니다.
        """
        self.agents.append(agent_handler)

    async def process_turn(self, turn: dict, session_id: str, **kwargs):
        """
        등록된 모든 에이전트를 병렬 실행하며, 완료되는 순서대로 결과를 yield 합니다. (Async Generator)
        """
        if not self.agents:
            return

        # 모든 에이전트 작업을 병렬로 생성
        tasks = [agent(turn, session_id, **kwargs) for agent in self.agents]
        
        # 완료되는 대로 결과 반환 (as_completed)
        for completed_task in asyncio.as_completed(tasks):
            try:
                res = await completed_task
                
                # None이 아니고 'skip'이 아닌 유효한 결과만 yield
                # 대규님 만약 마케팅 관련 내용을 생성한다면 state에 next_step 속성을 추가하셔야 할 것 같습니다.
                # 일단 추가 안해도 되도록 구현했습니다. 이해가 안되면 편하게 말씀해주세요
                # 만약 다른 방법이 있다면 알려주세요.
                if res and res.get("next_step", "generate") != "skip":
                    yield res
                else:
                    print("skip되어 프론트로 안 넘어감") # 디버깅용
            
            except Exception as e:
                print(f"Agent execution error: {e}")
                continue

# 싱글톤 인스턴스
agent_manager = AgentManager()
