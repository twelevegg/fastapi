from app.schemas.analysis import CallAnalysisResult
from app.core.exceptions import OpenAIException
from app.services.openai_service import client

class AnalysisService:
    async def analyze_conversation(self, transcript: list) -> CallAnalysisResult:
        """
        상담 스크립트를 분석하여 요약, 점수, 키워드 등을 추출합니다.
        """
        if not transcript:
            # 빈 결과 반환
            return CallAnalysisResult(
                summary_text="", estimated_cost=0, ces_score=0.0, 
                csat_score=0.0, rps_score=0.0, keyword=[], violence_count=0
            )
            
        # 대화 내용 포맷팅
        formatted_transcript = "\n".join([f"{t['speaker']}: {t['transcript']}" for t in transcript])
        
        system_prompt = """
        당신은 숙련된 CS 품질 관리자입니다. 
        제공된 상담 스크립트를 분석하여 다음 항목들을 추출/평가해 주세요.
        
        1. 요약: 상담의 핵심 내용을 명확하게 요약
        2. 추정 비용: 상담 내용을 바탕으로 예상되는 비용(상품 가입 등)이 있다면 원 단위로 추정 (없으면 0)
        3. CES (Customer Effort Score): 고객이 문제를 해결하기 위해 얼마나 많은 노력을 들였는지 0~10점으로 평가 (낮을수록 좋음, 즉 노력이 적게 듦)
        4. CSAT (Customer Satisfaction Score): 고객의 만족도를 0~100점으로 평가
        5. NPS/RPS (Net Promoter Score): 고객이 서비스를 추천할 의향을 0~10점으로 평가
        6. 키워드: 핵심 단어 리스트 추출
        7. 폭언 횟수: 고객의 발화 중 비속어, 욕설, 인신공격 등이 포함된 횟수 카운트
        """
        
        try:
            completion = await client.beta.chat.completions.parse(
                model="gpt-4o-mini", # Structured Output 지원 모델
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_transcript}
                ],
                response_format=CallAnalysisResult,
            )
            return completion.choices[0].message.parsed
            
        except Exception as e:
            # 로깅 추가 가능
            print(f"Analysis Error: {e}")
            raise OpenAIException(f"OpenAI Analysis Error: {str(e)}")

analysis_service = AnalysisService()
