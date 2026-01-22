
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Optional
import json

from app.agent.check import get_agent_response

router = APIRouter()


# ws://127.0.0.1:8000/api/v1/agent/check 여기에 연결!
@router.websocket("/check")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 클라이언트로부터 JSON 데이터 수신
            data = await websocket.receive_json()
            
            if "callId" in data and "clientId" in data:
                print(f"Call metadata received: {data['callId']}")
                # 메타데이터 받음 //TODO
                await websocket.send_json({"status": "received", "type": "metadata", "callId": data['callId']})
                continue
            
            # 2. Turn (Conversation turn)
            if "transcript" in data:
                transcript = data["transcript"]
                if not transcript:
                    continue
                    
                print(f"Processing turn {data.get('turn_id')}: {transcript}")
                
                try:
                    # get_agent_response 호출 (동기 함수)
                    results = get_agent_response(transcript)
                    
                    # 결과 전송
                    response = {
                        "type": "result",
                        "turn_id": data.get("turn_id"),
                        "results": results
                    }
                    await websocket.send_json(response)
                except Exception as e:
                    await websocket.send_json({"status": "error", "message": str(e)})
            
            else:
                print(f"Unknown data structure received: {data.keys()}")

    except WebSocketDisconnect:
        print("Client disconnected")
    except json.JSONDecodeError:
        print("Received non-JSON data")
        await websocket.close(code=1003)
