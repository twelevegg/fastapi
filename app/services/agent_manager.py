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

    async def process_turn(self, turn: dict, session_id: str, **kwargs) -> List[Dict[str, Any]]:
        """
        등록된 모든 에이전트에게 턴을 브로드캐스트하고 결과를 수집합니다.
        """
        if not self.agents:
            return []

        # 모든 에이전트를 병렬로 실행
        tasks = [agent(turn, session_id, **kwargs) for agent in self.agents]
        
        # 예외 발생 시에도 다른 에이전트는 계속 실행되도록 return_exceptions=True 사용
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for res in results:
            if isinstance(res, Exception):
                print(f"Agent execution error: {res}")
                continue
            
            # None이 아니고 'skip'이 아닌 유효한 결과만 수집
            if res and res.get("next_step") != "skip":
                valid_results.append(res)
                
        return valid_results

    async def process_turn_stream(self, turn: dict, session_id: str, **kwargs):
        """
        등록된 모든 에이전트를 병렬로 실행하고, 완료되는 순서대로 결과를 yield합니다.
        (Streaming Response)
        """
        if not self.agents:
            return

        # 모든 에이전트를 병렬로 실행
        tasks = [agent(turn, session_id, **kwargs) for agent in self.agents]
        
        # 완료되는 순서대로 처리
        for future in asyncio.as_completed(tasks):
            try:
                res = await future
                if isinstance(res, Exception):
                    print(f"Agent execution error: {res}")
                    continue
                
                # None이 아니고 'skip'이 아닌 유효한 결과만 yield
                if res and res.get("next_step") != "skip":
                    yield res
                    
            except Exception as e:
                print(f"Agent execution error (unhandled): {e}")

# 싱글톤 인스턴스
agent_manager = AgentManager()
