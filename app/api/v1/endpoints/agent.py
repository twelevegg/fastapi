
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Optional
import json
import uuid

from app.services.guidance_service import handle_guidance_message
from app.services.marketing_service import handle_marketing_message
from app.services.agent_manager import agent_manager
from app.services.connection_manager import connection_manager
from app.services.notification_manager import notification_manager

# 에이전트 등록 (서버 시작 시 또는 모듈 로드 시)
agent_manager.register_agent(handle_guidance_message)
agent_manager.register_agent(handle_marketing_message) # Marketing Agent 등록 완료


router = APIRouter()

@router.websocket("/monitor/{call_id}")
async def monitor_endpoint(websocket: WebSocket, call_id: str):
    await connection_manager.connect(websocket, call_id)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, call_id)
        print(f"Monitor client disconnected from {call_id}")

@router.websocket("/notifications/{user_id}")
async def notification_endpoint(websocket: WebSocket, user_id: str):
    await notification_manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive (heartbeat)
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_manager.disconnect(websocket, user_id)
        print(f"Notification client {user_id} disconnected")

@router.websocket("/check")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_session_id = str(uuid.uuid4())
    print(f"Agent WebSocket Connected. Session ID: {current_session_id}")
    
    # 고객 정보 (예시) - 실제로는 DB에서 조회 - 지금은 Mock데이터임
    customer_info = {"customer_id": "CUST-0001", "name": "김토스", "rate_plan": "유쓰 5G 심플+", "joined_date": "2023-05-20"}
    is_first_turn = True

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            raw_text = message.get("text")
            raw_bytes = message.get("bytes")

            if raw_text is not None:
                print(f"WS payload (session: {current_session_id}): {raw_text}")
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    print("Received non-JSON data")
                    await websocket.close(code=1003)
                    break
            elif raw_bytes is not None:
                print(f"WS binary payload (session: {current_session_id}): {len(raw_bytes)} bytes")
                print("Received non-JSON data")
                await websocket.close(code=1003)
                break
            elif message_type == "websocket.disconnect":
                raise WebSocketDisconnect
            else:
                print(f"WS unexpected message (session: {current_session_id}): {message}")
                continue
            
            # 1. Metadata Handling
            # 1. Metadata Handling
            if "callId" in data and "transcript" not in data:
                # 메타데이터에 callId가 있으면 이를 세션 ID로 사용
                current_session_id = data["callId"]
                print(f"Call metadata received: {current_session_id}")
                
                response_metadata = {"status": "received", "type": "metadata", "callId": current_session_id}
                print(f"WS response (session: {current_session_id}): {response_metadata}")
                await websocket.send_json(response_metadata)
                
                
                # 프론트엔드로 브로드캐스트 (해당 Call ID 방에만)
                await connection_manager.broadcast({
                    "type": "metadata_update",
                    "data": response_metadata
                }, call_id=current_session_id)
                
                # [NEW] 전체 유저(또는 특정 유저)에게 "새로운 통화 시작됨" 알림 전송
                # 실제로는 담당자 배정 로직에 따라 특정 유저에게만 보낼 수도 있음
                await notification_manager.broadcast({
                    "type": "CALL_STARTED",
                    "callId": current_session_id,
                    "customer_info": customer_info # 필요하다면 포함
                })
                
                continue
            
            # 2. Turn (Conversation turn)
            if "transcript" in data and "speaker" in data:
                transcript = data["transcript"]
                speaker = data["speaker"]
                turn_id = data.get("turn_id")

                print(f"Processing turn before {turn_id}: '{speaker}' {transcript}")

                await websocket.send_json({
                    "type": "transcript_update",
                    "data": {
                        "speaker": speaker,
                        "transcript": transcript,
                        "turn_id": turn_id,
                        "session_id": current_session_id
                    }
                })
                
                if not transcript or not speaker:
                    continue
                    
                print(f"Processing turn after {turn_id}: '{speaker}' {transcript}")
                
                # STT 수신 내용 브로드캐스트
                await connection_manager.broadcast({
                    "type": "transcript_update",
                    "data": {
                        "speaker": speaker,
                        "transcript": transcript,
                        "turn_id": turn_id,
                        "session_id": current_session_id
                    }
                }, call_id=current_session_id)
                
                try:
                    # 턴 데이터 구성(일단 에이전트한테 아래 데이터 3개만 보내도록 수정했습니다.)
                    turn_data = {
                        "speaker": speaker, 
                        "transcript": transcript, 
                        "turn_id": turn_id
                    }
                    
                    # Agent Manager를 통해 에이전트 병렬 실행 (스트리밍)
                    info_to_send = customer_info if is_first_turn else None
                    
                    is_first_turn = False
                    
                    async for result in agent_manager.process_turn(
                        turn=turn_data,
                        session_id=current_session_id,
                        customer_info=info_to_send
                    ):
                        # 결과 전송
                        response = {
                            "type": "result",
                            "agent_type": result.get("agent_type", "unknown"),
                            "turn_id": turn_id,
                            "results": result 
                        }
                        print(f"WS response (session: {current_session_id}): {response}")
                        await websocket.send_json(response)
                    
                        is_first_turn = False
                        
                        # 결과 브로드캐스트
                        await connection_manager.broadcast(response, call_id=current_session_id)
                        
                        print("웹소켓으로 전송 완료", response) # 디버깅용
                        
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    print(f"Error processing turn: {e}")
                    error_response = {"status": "error", "message": str(e)}
                    print(f"WS response (session: {current_session_id}): {error_response}")
                    await websocket.send_json(error_response)
            
            else:
                 # 알 수 없는 데이터 구조는 로그만 남기고 스킵
                 pass

    except WebSocketDisconnect:
        print(f"Client disconnected (Session: {current_session_id})")
        
        # [DEBUG] Client disconnected
        pass
        
    except json.JSONDecodeError:
        print("Received non-JSON data")
        await websocket.close(code=1003)
