from typing import List, Dict, Optional
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Call ID를 키로 하고 연결된 웹소켓 리스트를 값으로 저장
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, call_id: str):
        await websocket.accept()
        if call_id not in self.active_connections:
            self.active_connections[call_id] = []
        self.active_connections[call_id].append(websocket)
        print(f"Monitor connected to call {call_id}. Active sessions: {list(self.active_connections.keys())}")

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

connection_manager = ConnectionManager()
