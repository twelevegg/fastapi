from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
from app.agent.marketing_bridge import process_marketing_turn

router = APIRouter()

@router.websocket("/marketing")
async def websocket_marketing(websocket: WebSocket):
    """
    New Dedicated Channel for CS Marketing AI
    Connect: /api/v1/agent/marketing
    """
    await websocket.accept()
    print("[Marketing] Client Connected")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Simple Protocol: {"transcript": "...", "turn_id": 1}
            transcript = data.get("transcript")
            turn_id = data.get("turn_id", 0)
            
            if not transcript:
                continue
                
            print(f"[Marketing] Received: {transcript}")
            
            # Call Bridge (Async)
            try:
                result = await process_marketing_turn(transcript, turn_id)
                
                # Send Response
                # Customize response format as needed by Frontend
                response = {
                    "type": "marketing_result",
                    "turn_id": turn_id,
                    "data": result
                }
                await websocket.send_json(response)
                
            except Exception as e:
                print(f"[Marketing] Error: {e}")
                await websocket.send_json({"status": "error", "message": str(e)})
                
    except WebSocketDisconnect:
        print("[Marketing] Client Disconnected")
    except Exception as e:
        print(f"[Marketing] Critical Error: {e}")
        try:
            await websocket.close()
        except:
            pass
