from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.guidance_service import handle_guidance_message
import json
import uuid
import asyncio

router = APIRouter()

# Mock DB 함수
async def get_customer_info_from_db():
    # 실제 DB 연동 시 비동기 호출 시뮬레이션
    await asyncio.sleep(0.1) 
    return {"name": "김고객", "rate_plan": "5G 프리미어", "joined_date": "2023-05-20"}

@router.websocket("/guidance")
async def websocket_guidance(websocket: WebSocket):
    await websocket.accept()

    # 세션 ID 생성
    session_id = str(uuid.uuid4())
    print(f"Guidance WebSocket 연결: {session_id}")

    # 연결 초기: 고객 정보 조회
    customer_info = await get_customer_info_from_db()
    print(f"고객 정보: {customer_info}")

    # 첫 번째 턴인지 확인하는 플래그
    is_first_turn = True

    try:
        while True:
            # WebSocket으로 메시지 수신(JSON)
            turns = await websocket.receive_json()

            # 빈 리스트면 스킵
            if not turns:
                continue

            # 첫 번째 턴이면 고객 정보 전달
            info_to_send = customer_info if is_first_turn else None
            result = await handle_guidance_message(
                turns=turns, 
                session_id=session_id, 
                customer_info=info_to_send
                    )
            
            is_first_turn = False
            
            # 결과 메시지 전송
            response = {
                "session_id": session_id,
                "recommended_answer": result.get("recommended_answer"),
                "work_guide": result.get("work_guide"),
            }
            await websocket.send_json(response)

    except WebSocketDisconnect:
        print(f"Guidance WebSocket 연결 종료: {session_id}")
    except Exception as e:
        print(f"Guidance WebSocket 오류: {e}")
        # 에러가 발생해도 연결을 끊지 않고 에러 미시지 전송 시도
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass