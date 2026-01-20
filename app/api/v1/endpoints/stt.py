from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stt_service import stt_service
from app.core.exceptions import STTException

router = APIRouter()

@router.websocket("/stt")
async def websocket_stt(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive audio bytes from the client
            audio_data = await websocket.receive_bytes()
            
            # Process STT
            try:
                text = await stt_service.transcribe_audio(audio_data)
                await websocket.send_text(text)
            except STTException as e:
                await websocket.send_text(f"Error: {str(e)}")
                
    except WebSocketDisconnect:
        print("Client disconnected")
