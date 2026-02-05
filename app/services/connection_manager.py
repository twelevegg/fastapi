from typing import List, Dict, Optional
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Call ID를 키로 하고 연결된 웹소켓 리스트를 값으로 저장
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # [NEW] Call ID별 대화 이력 및 고객 정보 저장 (분석 로직 트리거용)
        self.call_history: Dict[str, List[Dict]] = {}
        self.call_customer_info: Dict[str, Dict] = {}
        # [NEW] Call ID별 담당 상담원 정보 (member_id, tenant_name)
        self.call_member_id: Dict[str, Dict] = {}
        # [NEW] Call ID별 시작 시간 저장
        self.call_start_times: Dict[str, object] = {}

    async def connect(self, websocket: WebSocket, call_id: str):
        await websocket.accept()
        if call_id not in self.active_connections:
            self.active_connections[call_id] = []
        self.active_connections[call_id].append(websocket)
        print(f"Monitor connected to call {call_id}. Active sessions: {list(self.active_connections.keys())}")

    def add_transcript(self, call_id: str, transcript_data: dict):
        if call_id not in self.call_history:
            self.call_history[call_id] = []
        self.call_history[call_id].append(transcript_data)

    def set_customer_info(self, call_id: str, info: dict):
        self.call_customer_info[call_id] = info

    def set_member_id(self, call_id: str, member_id: int, tenant_name: str = "default"):
        self.call_member_id[call_id] = {"member_id": member_id, "tenant_name": tenant_name}
        print(f"[ConnectionManager] Member mapped: Call {call_id} -> Member {member_id} (Tenant: {tenant_name})")

    def get_history(self, call_id: str) -> List[Dict]:
        return self.call_history.get(call_id, [])

    def get_customer_info(self, call_id: str) -> Optional[Dict]:
        return self.call_customer_info.get(call_id)

    def get_member_id(self, call_id: str) -> Optional[Dict]:
        return self.call_member_id.get(call_id)


    def disconnect(self, websocket: WebSocket, call_id: str):
        if call_id in self.active_connections:
            if websocket in self.active_connections[call_id]:
                self.active_connections[call_id].remove(websocket)
            
            # 더 이상 연결된 관리자가 없으면 키 삭제
            if not self.active_connections[call_id]:
                del self.active_connections[call_id]
                print(f"Call {call_id} session cleared.")

    async def broadcast(self, message: dict, call_id: str):
        if call_id in self.active_connections:
            # 연결 리스트 복사하여 순회 (도중에 연결 끊김 처리가 발생할 수 있으므로)
            for connection in self.active_connections[call_id][:]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"Error broadcasting to client in {call_id}: {e}")
                    # 여기서 끊는 로직을 넣을 수도 있지만, disconnect 호출되는 흐름에 맡김
                    # 필요하다면 self.disconnect(connection, call_id) 호출

    # [NEW] 통화 시작 시간 관리
    def set_start_time(self, call_id: str):
        from datetime import datetime
        self.call_start_times[call_id] = datetime.now()
        print(f"Call {call_id} started at {self.call_start_times[call_id]}")

    def get_start_time(self, call_id: str):
        return self.call_start_times.get(call_id)

connection_manager = ConnectionManager()
