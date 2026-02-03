
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from typing import List, Optional
import json
import uuid

from app.services.guidance_service import handle_guidance_message
from app.services.marketing_service import handle_marketing_message
from app.services.agent_manager import agent_manager
from app.services.connection_manager import connection_manager
from app.services.notification_manager import notification_manager
from app.services.spring_connector import spring_connector
from app.services.analysis_service import analysis_service

# 에이전트 등록 (서버 시작 시 또는 모듈 로드 시)
agent_manager.register_agent(handle_guidance_message)
agent_manager.register_agent(handle_marketing_message) # Marketing Agent 등록 완료


router = APIRouter()

@router.post("/broadcast")
async def broadcast_event(request: Request):
    """
    외부 서비스(Node.js 등)에서 알림을 트리거하기 위한 HTTP 엔드포인트
    예: 전화가 울릴 때(Ring) 미리 팝업을 띄우기 위해 사용
    """
    data = await request.json()
    # print(f"Broadcast request received: {data.get('type')}")
    await notification_manager.broadcast(data)
    return {"status": "ok"}

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
    
    # 기본 고객 정보 (Spring 조회 실패 시 사용)
    customer_info = {"customer_id": "UNKNOWN", "name": "알 수 없음", "rate_plan": "Basic", "joined_date": "2024-01-01"}
    is_first_turn = True
    customer_number = None 
    conversation_history = []
    turn_counter = 0 # [NEW] 턴 카운터

    # [NEW] Background task for processing turns non-blocking
    async def process_turn_background(turn_data, session_id, customer_info_arg, turn_id):
        try:
            # [Optimization] 처리 시작 알림 (프론트엔드에서 '생성 중...' 표시 가능)
            processing_event = {
                "type": "processing",
                "turn_id": turn_id,
                "agent_type": "guidance" # Default assignee
            }
            # [FIX] AWS 서버(Asterisk)가 수신 루프가 없어 버퍼가 꽉 차는 문제 방지
            # 소스 소켓(Asterisk)으로는 데이터를 보내지 않고, 프론트엔드로만 브로드캐스트합니다.
            # try:
            #     await websocket.send_json(processing_event)
            # except: 
            #     pass
            await connection_manager.broadcast(processing_event, call_id=session_id)

            async for result in agent_manager.process_turn(
                turn=turn_data,
                session_id=session_id,
                customer_info=customer_info_arg
            ):
                response = {
                    "type": "result",
                    "agent_type": result.get("agent_type", "unknown"),
                    "turn_id": turn_id,
                    "results": result 
                }
                
                # [FIX] AWS 버퍼 오버플로우 방지를 위해 Asterisk로의 직접 전송 중단
                # try:
                #     await websocket.send_json(response)
                # except (RuntimeError, WebSocketDisconnect):
                #      # 소켓이 이미 닫힌 경우 무시 (로그 남기지 않음)
                #      break 
                # except Exception as e:
                #      # 그 외 에러는 로그 남기되, 연결 관련이면 무시 추정
                #      if "Unexpected ASGI message" in str(e) or "closed" in str(e):
                #          break
                #      print(f"Error sending response for turn {turn_id}: {e}")
                #      break

                await connection_manager.broadcast(response, call_id=session_id)

        except Exception as e:
             print(f"Error in background processing for turn {turn_id}: {e}")

    try:
        import asyncio # Import inside scope is fine, but better at top. logic kept here for replace simplicity
        while True:
            try:
                message = await websocket.receive()
                message_type = message.get("type")
                raw_text = message.get("text")
                raw_bytes = message.get("bytes")

                if raw_text is not None:
                    # print(f"WS payload (session: {current_session_id}): {raw_text}")
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        print("Received non-JSON data")
                        await websocket.close(code=1003)
                        break
                elif raw_bytes is not None:
                    # print(f"WS binary payload (session: {current_session_id}): {len(raw_bytes)} bytes")
                    await websocket.close(code=1003)
                    break
                elif message_type == "websocket.disconnect":
                    raise WebSocketDisconnect
                else:
                    continue
                
                # 1. Metadata Handling
                received_call_id = data.get("callId") or data.get("call_id")
                if received_call_id and "transcript" not in data:
                    current_session_id = received_call_id
                    print(f"Call metadata received: {current_session_id}")

                    # [OPTIMIZATION] 팝업을 즉시 띄우기 위해 CALL_STARTED 먼저 전송
                    # 고객 정보는 아직 없으므로 기본값 또는 빈 값으로 보냄
                    await notification_manager.broadcast({
                        "type": "CALL_STARTED",
                        "callId": current_session_id,
                        "customer_info": {"name": "로딩중...", "rate_plan": "확인중..."} 
                    })

                    # [NEW] 고객 정보 조회 (Spring) - 비동기로 처리하여 팝업 지연 방지
                    customer_number = data.get("customer_number")
                    if customer_number:
                         # print(f"Fetching info for customer: {customer_number}")
                         fetched_info = await spring_connector.get_customer_info(customer_number)
                         if fetched_info:
                             customer_info = fetched_info.model_dump()
                             # print(f"Customer info loaded: {customer_info.get('name')}")
                             
                             # 정보가 로드되면 메타데이터 업데이트 이벤트 전송 (프론트에서 갱신하도록)
                             await notification_manager.broadcast({
                                "type": "CALL_UPDATED", # 프론트에서 이 타입을 처리해야 함 (또는 CALL_STARTED 다시 전송)
                                "callId": current_session_id,
                                "customer_info": customer_info
                            })
                         else:
                             print("Customer info fetch failed.")
                    
                    response_metadata = {"status": "received", "type": "metadata", "callId": current_session_id}
                    # [FIX] AWS 전송 중단
                    # await websocket.send_json(response_metadata)
                    
                    await connection_manager.broadcast({
                        "type": "metadata_update",
                        "data": response_metadata
                    }, call_id=current_session_id)
                    
                    continue
                
                # 2. Turn (Conversation turn)
                if "transcript" in data and "speaker" in data:
                    transcript = data["transcript"]
                    speaker = data["speaker"]
                    
                    # [FIX] turn_id가 없는 경우 자동 생성
                    turn_counter += 1
                    turn_id = data.get("turn_id")
                    if not turn_id:
                        turn_id = turn_counter

                    print(f"Processing turn {turn_id}: '{speaker}' {transcript}")

                    # 비상용: 메타데이터 누락 시 첫 턴에서 강제 시작 알림
                    if is_first_turn:
                         print(f"First turn received. Broadcasting CALL_STARTED fallback.")
                         await notification_manager.broadcast({
                            "type": "CALL_STARTED",
                            "callId": current_session_id,
                            "customer_info": customer_info
                        })

                    # [FIX] AWS 전송 중단 (프론트엔드 브로드캐스트만 유지)
                    # await websocket.send_json({
                    #     "type": "transcript_update",
                    #     "data": {
                    #         "speaker": speaker, 
                    #         "transcript": transcript, 
                    #         "turn_id": turn_id, 
                    #         "session_id": current_session_id
                    #     }
                    # })
                    
                    if not transcript or not speaker:
                        continue
                        
                    conversation_history.append({"speaker": speaker, "transcript": transcript})
                    
                    # STT 수신 내용 브로드캐스트
                    await connection_manager.broadcast({
                        "type": "transcript_update",
                        "data": {
                            "speaker": speaker, "transcript": transcript, 
                            "turn_id": turn_id, "session_id": current_session_id
                        }
                    }, call_id=current_session_id)
                    
                    # [FIX] 비동기 백그라운드 처리 (Create Task)
                    turn_data = {"speaker": speaker, "transcript": transcript, "turn_id": turn_id}
                    info_to_send = customer_info if is_first_turn else None
                    
                    asyncio.create_task(process_turn_background(
                        turn_data, 
                        current_session_id, 
                        info_to_send,
                        turn_id
                    ))
                    
                    is_first_turn = False
                
                else:
                     pass
                     
            except WebSocketDisconnect:
                raise
            except Exception as e:
                print(f"Error processing message in main loop: {e}")
                # Continue loop despite error

    except WebSocketDisconnect:
        print(f"Client disconnected (Session: {current_session_id})")
        
        await notification_manager.broadcast({
            "type": "CALL_ENDED",
            "callId": current_session_id
        })
        
        if conversation_history:
            print(f"Call {current_session_id} ended. Generating comprehensive analysis...")
            try:
                analysis_result = await analysis_service.analyze_conversation(conversation_history)
                print(f"Analysis complete: {analysis_result.summary_text[:50]}...")
                
                payload = {
                    "transcripts": conversation_history,
                    "summary_text": analysis_result.summary_text,
                    "estimated_cost": analysis_result.estimated_cost,
                    "ces_score": analysis_result.ces_score,
                    "csat_score": analysis_result.csat_score,
                    "rps_score": analysis_result.rps_score,
                    "keyword": analysis_result.keyword,
                    "violence_count": analysis_result.violence_count,
                    "customer_number": customer_number
                }
                
                await spring_connector.send_call_data(payload)
                
            except Exception as e:
                print(f"Error during call end processing: {e}")

    except json.JSONDecodeError:
        print("Received non-JSON data")
        await websocket.close(code=1003)
