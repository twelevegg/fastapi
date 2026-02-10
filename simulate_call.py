
import asyncio
import websockets
import json
import uuid
import random

async def simulate_call():
    # uri = "ws://13.209.17.129:8000/ai/api/v1/agent/check"
    uri = "ws://localhost:8000/ai/api/v1/agent/check"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to {uri}")
            
            # 1. Simulate Call Metadata (Call Started)
            call_id = f"call-{uuid.uuid4().hex[:8]}"
            metadata = {
                "callId": call_id, 
                "customer_number": "010-9876-4321", # [NEW] Spring 조회용 번호
                "customer_info": {
                    "customer_id": "cust_kt_002", 
                    "name": "박민수", 
                    "rate_plan": "KT 5G 프리미엄"
                }
            }
            
            await websocket.send(json.dumps(metadata))
            print(f"Sent metadata: {metadata}")
            
            print("Wait 1 seconds before sending dialogue...")
            await asyncio.sleep(1)
            
            # 2. Simulate Conversation Turns (KT Family Combination Scenario)
            turns = [
                {"turn_id": 1, "speaker": "agent", "transcript": "반갑습니다. KT 고객센터 상담사 정하나입니다. 무엇을 도와드릴까요?"},
                {"turn_id": 2, "speaker": "customer", "transcript": "안녕하세요. 이번에 가족들 휴대폰을 다 KT로 바꿔서 가족 결합 할인을 좀 받으려고 전화드렸어요."},
                {"turn_id": 3, "speaker": "agent", "transcript": "네, 고객님. 휴대폰 회선 결합 상담 도와드리겠습니다. 현재 인터넷은 어떤 상품 사용 중이신가요?"},
                {"turn_id": 4, "speaker": "customer", "transcript": "인터넷은 지금 1기가 상품 쓰고 있고요. 휴대폰은 저랑 와이프, 애들 둘까지 해서 총 4명이 다 KT예요."},
                {"turn_id": 5, "speaker": "customer", "transcript": "이게 '프리미엄 가족 결합'인가 그걸로 하면 1인당 휴대폰 할인 금액이 정확히 얼마씩 나오나요? 그리고 제 동생이 알뜰폰 쓰는데 그것도 되는지 궁금해서요."},
                {"turn_id": 6, "speaker": "agent", "transcript": "네, '프리미엄 가족 결합'의 경우 구성원 모두 베이직 이상 요금제를 쓰시면, 2회선부터 최대 50%까지 할인이 가능합니다. 알뜰폰의 경우 KT망을 사용하면 결합 회선 수에는 포함되지만, 요금 할인은 제외될 수 있어 확인이 필요합니다. 동생분 통신사가 어디실까요?"}, 
                {"turn_id": 7, "speaker": "customer", "transcript": "아, 동생은 'KT 엠모바일' 쓴다고 했어요. KT망이라고는 하더라고요. 그럼 할인 안돼도 회선 수로는 잡히는 거죠?"},
                {"turn_id": 8, "speaker": "agent", "transcript": "네, 맞습니다! KT 엠모바일은 KT망 알뜰폰이라 결합 회선 수 산정에 포함되어, 고객님과 다른 가족분들의 할인 자격을 유지하는 데 도움이 됩니다."},
                {"turn_id": 9, "speaker": "customer", "transcript": "그렇구나. 그리고 인터넷도 지금 약정이 거의 다 끝나가는데, 이거 재약정하면서 결합하면 상품권 같은 것도 주나요?"},
                {"turn_id": 10, "speaker": "agent", "transcript": "네, 마침 약정이 1개월 남으셨네요. 지금 재약정과 함께 결합을 진행하시면, 와이파이 공유기를 최신 '기가 와이파이 6' 모델로 무상 교체해 드리고, 추가 사은품도 챙겨드릴 수 있습니다."},
                {"turn_id": 11, "speaker": "customer", "transcript": "오, 공유기 교체 좋네요. 근데 요즘 넷플릭스를 많이 봐서, 넷플릭스 포함된 요금제나 그런 건 없나요? 인터넷 티비 쪽으로요."},
                {"turn_id": 12, "speaker": "agent", "transcript": "탁월한 선택이십니다. '지니 TV 넷플릭스 초이스' 요금제가 있습니다. 모바일 결합까지 하시면 월 1만 원대로 넷플릭스 HD 화질을 이용하실 수 있게 설계해 드릴 수 있습니다."},
                {"turn_id": 13, "speaker": "customer", "transcript": "1만 원대면 꽤 괜찮네요. 지금 보고 있는 셋톱박스도 좀 오래돼서 반응이 느린데, 이것도 바꿔주시나요?"},
                {"turn_id": 14, "speaker": "agent", "transcript": "물론입니다. 이번에 최신 '기가지니3' 셋톱박스로 변경해 드립니다. 반응 속도도 훨씬 빠르고 유튜브나 넷플릭스 앱 실행도 음성으로 바로 가능하십니다."},
                {"turn_id": 15, "speaker": "customer", "transcript": "좋네요. 그럼 그걸로 다 묶어서 진행해 주세요. 알뜰폰 쓰는 동생 서류는 나중에 보내면 되나요?"},
                {"turn_id": 16, "speaker": "agent", "transcript": "네, 결정 감사합니다! 동생분 가족관계 증명서만 문자로 보내주시는 링크로 첨부해 주시면 됩니다. 바로 접수 도와드리겠습니다."},
                {"turn_id": 17, "speaker": "customer", "transcript": "네 알겠습니다. 감사합니다 수고하세요."},
                {"turn_id": 18, "speaker": "agent", "transcript": "네 고객님, 오늘도 좋은 하루 되세요. 상담사 정하나였습니다."}
            ]
            
            for i, turn in enumerate(turns):
                # Remove extra long thinking pauses for consistent log flow
                # if i == 5:
                #      print("\n--- Simulating 5s Thinking Pause ---\n")
                #      await asyncio.sleep(5)

                turn_data = {
                    "callId": call_id,
                    "speaker": turn["speaker"],
                    "transcript": turn["transcript"],
                    "turn_id": turn["turn_id"]
                }
                
                await websocket.send(json.dumps(turn_data))
                print(f"Sent turn {turn['turn_id']}: {turn['transcript'][:30]}...", flush=True)
                
                # Wait exactly 3 seconds as requested, flushing output to ensure real-time logging
                await asyncio.sleep(3)
            
            print("Simulation complete. Messages sent!", flush=True)
            print("Keeping connection alive for 1 hour... (Press Ctrl+C to stop)", flush=True)
            await asyncio.sleep(3600)
            print("Closing connection.", flush=True)
            
    except Exception as e:
        print(f"Connection failed: {e}", flush=True)
        print("Make sure the FastAPI server is running at localhost:8000", flush=True)

if __name__ == "__main__":
    asyncio.run(simulate_call())
