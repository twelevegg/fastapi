
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Optional
import json
import uuid

from app.services.guidance_service import handle_guidance_message
from app.services.agent_manager import agent_manager

# 에이전트 등록 (서버 시작 시 또는 모듈 로드 시)
agent_manager.register_agent(handle_guidance_message)
# agent_manager.register_agent(handle_marketing_message) # 여기에 마케팅 에이전트 돌리는 함수 등록하면 됩니다.


router = APIRouter()

@router.websocket("/check")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # 기본 세션 ID 생성 (연결 시)
    current_session_id = str(uuid.uuid4())
    
    # 고객 정보 (예시) - 실제로는 DB에서 조회 - 지금은 Mock데이터임
    customer_info = {"name": "김고객", "rate_plan": "5G 프리미어", "joined_date": "2023-05-20"}
    is_first_turn = True

    try:
        while True:
            # 클라이언트로부터 JSON 데이터 수신
            data = await websocket.receive_json()
            
            # 1. Metadata Handling
            if "callId" in data:
                # 메타데이터에 callId가 있으면 이를 세션 ID로 사용
                current_session_id = data["callId"]
                print(f"Call metadata received: {current_session_id}")
                await websocket.send_json({"status": "received", "type": "metadata", "callId": current_session_id})
                continue
            
            # 2. Turn (Conversation turn)
            if "transcript" in data and "speaker" in data:
                transcript = data["transcript"]
                speaker = data["speaker"]
                turn_id = data.get("turn_id")
                
                if not transcript or not speaker:
                    continue
                    
                print(f"Processing turn {turn_id}: '{speaker}' {transcript}")
                
                try:
                    # 턴 데이터 구성(일단 에이전트한테 아래 데이터 3개만 보내도록 수정했습니다.)
                    turn_data = {
                        "speaker": speaker, 
                        "transcript": transcript, 
                        "turn_id": turn_id
                    }
                    
                    # Agent Manager를 통해 모든 에이전트 병렬 실행
                    info_to_send = customer_info if is_first_turn else None
                    
                    results = await agent_manager.process_turn(
                        turn=turn_data,
                        session_id=current_session_id,
                        customer_info=info_to_send
                    )
                    
                    is_first_turn = False
                    
                    # 수집된 유효 결과들을 전송
                    for result in results:
                        response = {
                            "type": "result",
                            "agent_type": result.get("agent_type", "unknown"),
                            "turn_id": turn_id,
                            "results": {
                                "recommended_answer": result.get("recommended_answer"),
                                "work_guide": result.get("work_guide"),
                                "next_step": result.get("next_step")
                            }
                        }
                        await websocket.send_json(response)
                        
                except Exception as e:
                    print(f"Error processing turn: {e}")
                    await websocket.send_json({"status": "error", "message": str(e)})
            
            else:
                 # 알 수 없는 데이터 구조는 로그만 남기고 스킵
                 pass

    except WebSocketDisconnect:
        print("Client disconnected")
    except json.JSONDecodeError:
        print("Received non-JSON data")
        await websocket.close(code=1003)
