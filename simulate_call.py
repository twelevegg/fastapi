
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
                {"turn_id": 1, "speaker": "agent", "transcript": "반갑습니다. LG U+ 고객센터 상담사 이종환입니다. 무엇을 도와드릴까요?"},
                {"turn_id": 2, "speaker": "customer", "transcript": "안녕하세요. 가족들이랑 통신사를 다 U+로 맞춰서 결합 할인을 좀 받으려고요. 그리고 데이터가 좀 부족한 것 같아서 요금제도 보고 싶어요."},
                {"turn_id": 3, "speaker": "agent", "transcript": "네, 고객님. 결합과 요금제 변경 모두 도와드리겠습니다. 현재 고객님께서는 '5G 데이터 레귤러' 요금제를 사용 중이시네요."},
                {"turn_id": 4, "speaker": "customer", "transcript": "네 맞아요. 50기가 정도 쓰는 것 같은데, 유튜브를 많이 봐서 그런지 월말 되면 항상 모자라더라고요."},
                {"turn_id": 5, "speaker": "agent", "transcript": "현재 50.0GB 사용 중이신데, 사용 패턴상 조금 부족할 수 있습니다. 80.0GB 제공되는 '5G 데이터 플러스' 요금제로 조정하시면 추가 충전 없이 훨씬 안정적으로 사용하실 수 있어요."},
                {"turn_id": 6, "speaker": "customer", "transcript": "오, 80기가면 충분하겠네요. 그걸로 바꾸는 게 낫겠어요. 그럼 가족 결합은 어떻게 하는 게 좋을까요?"},
                {"turn_id": 7, "speaker": "agent", "transcript": "가족분들 모두 U+ 모바일을 이용 중이시라면 'U+ 투게더 결합'을 추천드립니다. 모바일 회선 수에 따라 결합 할인을 크게 받으실 수 있습니다."},
                {"turn_id": 8, "speaker": "customer", "transcript": "그렇군요. 아, 그리고 제 동생은 알뜰폰 쓰는데 그것도 같이 묶을 수 있나요?"},
                {"turn_id": 9, "speaker": "agent", "transcript": "네, 알뜰폰의 경우 '참 쉬운 가족 결합'으로 진행하실 수 있습니다. 인터넷과 알뜰폰을 결합하여 추가 혜택을 받으실 수 있도록 설계해 드릴 수 있습니다."},
                {"turn_id": 10, "speaker": "customer", "transcript": "좋네요. 그럼 저는 '5G 데이터 플러스'로 바꾸고, 가족들은 투게더 결합이랑 참 쉬운 가족 결합으로 다 묶어주세요."},
                {"turn_id": 11, "speaker": "agent", "transcript": "네, 알겠습니다. '5G 데이터 플러스' 변경과 결합 상품 가입 즉시 처리해 드리겠습니다. 좋은 선택 감사드립니다."},
                {"turn_id": 12, "speaker": "customer", "transcript": "네 감사합니다. 수고하세요."}
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
