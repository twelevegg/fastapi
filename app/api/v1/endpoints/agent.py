
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from typing import List, Optional
import json
import uuid
import asyncio

from app.services.guidance_service import handle_guidance_message
from app.services.marketing_service import handle_marketing_message
from app.services.agent_manager import agent_manager
from app.services.connection_manager import connection_manager
from app.services.notification_manager import notification_manager
from app.services.spring_connector import spring_connector
from app.services.analysis_service import analysis_service
from app.utils.phone_number_generator import get_random_phone_number

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

# [NEW] 공통 분석 로직 추출
async def process_call_analysis(call_id: str):
    """
    전화 종료 시(또는 강제 종료 트리거 시) 분석을 수행하고 Spring으로 전송하는 함수
    """
    history = connection_manager.get_history(call_id)
    customer_info = connection_manager.get_customer_info(call_id)
    customer_number = customer_info.get("phoneNumber") if customer_info else None
    
    # [FIX] customer_info 내부에 phoneNumber가 없으면, 랜덤 생성했던 번호를 못 찾을 수도 있음.
    # 하지만 일단 connection_manager에 무엇을 저장했느냐에 따름.
    # 만약 customer_info 전체 딕셔너리를 저장했다면 phoneNumber 키가 없을 수도 있음. (Spring 응답 구조 확인 필요)
    # 일단 'customer_number' 별도 저장소 없이 customer_info에 의존.
    
    member_info = connection_manager.get_member_id(call_id)
    member_id = member_info.get("member_id") if member_info else None
    tenant_name = member_info.get("tenant_name") if member_info else None

    if not history:
        print(f"No conversation history for {call_id}. Skipping analysis.")
        return

    print(f"Processing Call Analysis for {call_id} (Length: {len(history)} turns)...")
    
    try:
        # [NEW] 시간 관련 데이터 계산
        from datetime import datetime
        start_time = connection_manager.get_start_time(call_id)
        end_time = datetime.now()
        duration = 0
        billsec = 0
        
        start_time_str = None
        end_time_str = end_time.isoformat()
        
        if start_time:
            start_time_str = start_time.isoformat()
            duration_delta = end_time - start_time
            duration = int(duration_delta.total_seconds())
            # 현재는 billsec = duration으로 처리 (추후 세분화 가능)
            billsec = duration*0.7
        
        # 분석 수행
        analysis_result = await analysis_service.analyze_conversation(history)
        print(f"Analysis complete: {analysis_result.summary_text[:50]}...")
        
        payload = {
            "transcripts": history,
            "summary_text": analysis_result.summary_text,
            "estimated_cost": analysis_result.estimated_cost,
            "ces_score": analysis_result.ces_score,
            "csat_score": analysis_result.csat_score,
            "rps_score": analysis_result.rps_score,
            "keyword": analysis_result.keyword,
            "violence_count": analysis_result.violence_count,
            "customer_number": customer_number,
            "member_id": member_id,
            "tenant_name": tenant_name,
            # [NEW] Time metrics
            "start_time": start_time_str,
            "end_time": end_time_str,
            "duration": duration,
            "billsec": billsec
        }
        
        # Spring 전송
        await spring_connector.send_call_data(payload)
        
        # 분석 완료 알림 등으로 UI 업데이트 가능 (선택)
        
    except Exception as e:
        print(f"Error during call end processing for {call_id}: {e}")


@router.websocket("/monitor/{call_id}")
async def monitor_endpoint(websocket: WebSocket, call_id: str):
    await connection_manager.connect(websocket, call_id)
    
    # [NEW] 통화 시작 시간 기록 (Monitor 연결 기준)
    # 이미 기록된 시간이 없을 때만 기록 (재연결 시 초기화 방지)
    if not connection_manager.get_start_time(call_id):
        connection_manager.set_start_time(call_id)
        print(f"Call start time recorded for {call_id} (Monitor Connected)")
    
    # [NEW] Frontend에서 메시지를 받을 수 있도록 Loop 추가
    try:
        while True:
            text = await websocket.receive_text()
            print(f"Monitor received: {text}")
            try:
                data = json.loads(text)
                if data.get("type") == "CALL_ENDED":
                    print(f"[Frontend Trigger] Explicit Call End for {call_id}")
                    await notification_manager.broadcast({
                        "type": "CALL_ENDED",
                        "callId": call_id
                    })
                    # 비동기로 분석 수행
                    asyncio.create_task(process_call_analysis(call_id))

                elif data.get("type") == "IDENTIFY":
                    member_id = data.get("memberId")
                    tenant_name = data.get("tenantName")
                    if member_id:
                        connection_manager.set_member_id(call_id, member_id, tenant_name or "default")
                        
            except json.JSONDecodeError:
                pass
                
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
    
    # [MOVED] 통화 시작 시간 기록은 monitor_endpoint로 이동함
    # connection_manager.set_start_time(current_session_id)
    
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
        while True:
            try:
                message = await websocket.receive()
                message_type = message.get("type")
                raw_text = message.get("text")
                raw_bytes = message.get("bytes")

                if raw_text is not None:
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        print("Received non-JSON data")
                        await websocket.close(code=1003)
                        break
                elif raw_bytes is not None:
                    await websocket.close(code=1003)
                    break
                elif message_type == "websocket.disconnect":
                    raise WebSocketDisconnect
                else:
                    continue
                
                # 1. Metadata Handling
                received_call_id = data.get("callId") or data.get("call_id")
                if received_call_id and "transcript" not in data:
                    print(f"Call metadata received: {received_call_id}")
                    
                    if received_call_id != current_session_id:
                        print(f"New session detected ({current_session_id} -> {received_call_id}). Resetting state.")
                        current_session_id = received_call_id
                        turn_counter = 0
                        conversation_history = []
                        is_first_turn = True
                        customer_info = {"customer_id": "UNKNOWN", "name": "알 수 없음", "rate_plan": "Basic", "joined_date": "2024-01-01"}
                    else:
                        print(f"Metadata received for existing session. Forcing reset for safety.")
                        turn_counter = 0
                        conversation_history = []
                        is_first_turn = True
                        
                    await notification_manager.broadcast({
                        "type": "CALL_STARTED",
                        "callId": current_session_id,
                        "customer_info": {"name": "로딩중...", "rate_plan": "확인중..."} 
                    })

                    customer_number = get_random_phone_number()
                    print(f"[DEMO] Selected Random Customer Number: {customer_number}")

                    if customer_number:
                         print(f"Fetching info for customer: {customer_number}")
                         fetched_info = await spring_connector.get_customer_info(customer_number)
                         if fetched_info:
                             customer_info = fetched_info.model_dump()
                             customer_info["phoneNumber"] = customer_number
                             connection_manager.set_customer_info(current_session_id, customer_info)
                             
                             await notification_manager.broadcast({
                                "type": "CALL_UPDATED", 
                                "callId": current_session_id,
                                "customer_info": customer_info
                            })
                         else:
                             print("Customer info fetch failed.")
                    
                    response_metadata = {"status": "received", "type": "metadata", "callId": current_session_id}
                    await connection_manager.broadcast({
                        "type": "metadata_update",
                        "data": response_metadata
                    }, call_id=current_session_id)
                    continue
                
                # 2. Turn (Conversation turn)
                if "transcript" in data and "speaker" in data:
                    transcript = data["transcript"]
                    speaker = data["speaker"]
                    
                    turn_counter += 1
                    turn_id = data.get("turn_id") or turn_counter

                    print(f"Processing turn {turn_id}: '{speaker}' {transcript}")

                    if is_first_turn:
                         print(f"First turn received. Executing fallback customer lookup.")
                         if not customer_number:
                             customer_number = get_random_phone_number()
                             fetched_info = await spring_connector.get_customer_info(customer_number)
                             if fetched_info:
                                 customer_info = fetched_info.model_dump()
                                 customer_info["phoneNumber"] = customer_number
                                 connection_manager.set_customer_info(current_session_id, customer_info)

                         await notification_manager.broadcast({
                            "type": "CALL_STARTED",
                            "callId": current_session_id,
                            "customer_info": customer_info
                        })

                    if not transcript or not speaker:
                        continue
                        
                    current_turn_obj = {"speaker": speaker, "transcript": transcript}   
                    conversation_history.append(current_turn_obj)
                    connection_manager.add_transcript(current_session_id, current_turn_obj)
                    
                    await connection_manager.broadcast({
                        "type": "transcript_update",
                        "data": {
                            "speaker": speaker, "transcript": transcript, 
                            "turn_id": turn_id, "session_id": current_session_id
                        }
                    }, call_id=current_session_id)
                    
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
                print(f"WebSocket disconnected (Session: {current_session_id})")
                break
            except Exception as e:
                print(f"Error processing message in main loop: {e}")
                # 에러 발생 시 루프를 종료하여 cleanup(finally)으로 이동합니다.
                break

    except Exception as e:
        print(f"Unexpected error in websocket_endpoint: {e}")
    finally:
        # [CLEANUP] 모든 종료 상황(정상 종료, 에러, 연결 끊김)에서 실행됩니다.
        print(f"Cleaning up session: {current_session_id}")
        
        await notification_manager.broadcast({
            "type": "CALL_ENDED",
            "callId": current_session_id
        })
        
        if conversation_history:
             print(f"[Cleanup] Triggering analysis for {current_session_id}")
             asyncio.create_task(process_call_analysis(current_session_id))
        
        try:
            await websocket.close()
        except:
             pass
