from typing import List, Dict, Optional
from fastapi import WebSocket

class NotificationManager:
    def __init__(self):
        # User ID를 키로 하고 연결된 웹소켓 리스트를 값으로 저장
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"Notification Service: User {user_id} connected.")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def broadcast(self, message: dict, user_id: str = None):
        """
        user_id가 있으면 해당 유저에게만, 없으면 전체 유저에게 브로드캐스트
        """
        if user_id:
            if user_id in self.active_connections:
                for connection in self.active_connections[user_id]:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"Error sending notification to {user_id}: {e}")
        else:
            for uid, connections in self.active_connections.items():
                for connection in connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"Error sending notification to {uid}: {e}")

notification_manager = NotificationManager()
