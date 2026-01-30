
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
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
    customer_number = None 
    conversation_history = [] # [NEW] Initialize history list

    try:
        while True:
            # 클라이언트로부터 JSON 데이터 수신
            data = await websocket.receive_json()
            
            # 1. Metadata Handling
            if "callId" in data and "transcript" not in data:
                # 메타데이터에 callId가 있으면 이를 세션 ID로 사용
                current_session_id = data["callId"]
                print(f"Call metadata received: {current_session_id}")

                # [NEW] 고객 정보 조회 (Spring)
                customer_number = data.get("customer_number")
                if customer_number:
                     print(f"Fetching info for customer: {customer_number}")
                     fetched_info = await spring_connector.get_customer_info(customer_number)
                     if fetched_info:
                         # Pydantic 모델을 dict로 변환 (alias=True 옵션으로 한국어 키로 변환 가능하지만,
                         # 내부 로직에서는 영문 키를 사용하는 것이 일반적.
                         # 하지만 프론트엔드가 뭘 기대하느냐에 따라 다름.
                         # 일단 model_dump()로 변환해서 저장.
                         customer_info = fetched_info.model_dump()
                         print(f"Customer info loaded: {customer_info.get('name')}")
                     else:
                         print("Customer info fetch failed or not found.")
                else:
                    print("No customer_number provided in metadata.")
                
                response_metadata = {"status": "received", "type": "metadata", "callId": current_session_id}
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
                
                if not transcript or not speaker:
                    continue
                    
                # 대화 기록에 추가
                conversation_history.append({"speaker": speaker, "transcript": transcript})
                
                print(f"Processing turn {turn_id}: '{speaker}' {transcript}")
                
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
                        await websocket.send_json(response)
                    
                        is_first_turn = False
                        
                        # 결과 브로드캐스트
                        await connection_manager.broadcast(response, call_id=current_session_id)
                        
                        print("웹소켓으로 전송 완료", response) # 디버깅용
                        
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    print(f"Error processing turn: {e}")
                    await websocket.send_json({"status": "error", "message": str(e)})
            
            else:
                 # 알 수 없는 데이터 구조는 로그만 남기고 스킵
                 pass

    except WebSocketDisconnect:
        print(f"Client disconnected (Session: {current_session_id})")
        
        # [DEBUG] Client disconnected
        
        # [NEW] 통화 종료 시 종합 분석 및 Spring 전송 로직
        if conversation_history:
            print(f"Call {current_session_id} ended. Generating comprehensive analysis...")
            
            # 1. 종합 분석 생성
            try:
                # analysis_service를 통해 분석 수행
                analysis_result = await analysis_service.analyze_conversation(conversation_history)
                print(f"Analysis complete: {analysis_result.summary_text[:50]}...")
                
                # 2. Spring 서버로 데이터 전송
                payload = {
                    # CallAnalysisResult 모델의 필드를 dict로 변환 (model_dump 사용 가능)
                    "transcripts": conversation_history, # 상담 전문
                    "summary_text": analysis_result.summary_text,
                    "estimated_cost": analysis_result.estimated_cost,
                    "ces_score": analysis_result.ces_score,
                    "csat_score": analysis_result.csat_score,
                    "rps_score": analysis_result.rps_score,
                    "keyword": analysis_result.keyword,
                    "violence_count": analysis_result.violence_count,
                    "customer_number": customer_number # [NEW] 고객 전화번호 추가
                    # 필요하다면 추가 정보
                    # "callId": current_session_id,
                    # "customerInfo": customer_info
                }
                
                # 비동기 전송
                await spring_connector.send_call_data(payload)
                
            except Exception as e:
                print(f"Error during call end processing: {e}")

        
    except json.JSONDecodeError:
        print("Received non-JSON data")
        await websocket.close(code=1003)
