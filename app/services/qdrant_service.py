from langchain_core.documents import Document
from typing import List, Tuple, Any, Optional

# [MOCK MODE] t3.small 메모리 부족(OOM)으로 인해 검색 기능을 가짜(Mock)로 대체
# 실제 모델을 로드하지 않으므로 메모리를 거의 사용하지 않음 (0MB)
class MockQdrantVectorStore:
    async def asimilarity_search_with_score(self, query: str, k: int = 4, filter: Any = None) -> List[Tuple[Document, float]]:
        # [MOCK DATA LIBRARY: KT 버전] 실감나는 시연을 위한 확장 데이터
        mock_docs = [
            # 1. 상품/요금제 (Upsell - KT)
            (Document(page_content="5G 초이스 베이직: 월 90,000원, 데이터 완전 무제한, 멤버십 VVIP 등급 제공. 스마트기기 1회선 무료.", 
                      metadata={"category": "marketing", "title": "5G 초이스 베이직", "source": "RecSys_KT"}), 0.96),
            (Document(page_content="넷플릭스 초이스 스페셜: 월 110,000원. 넷플릭스 스탠다드 이용권 제공. 데이터 완전 무제한 + VVIP 멤버십.", 
                      metadata={"category": "marketing", "title": "넷플릭스 초이스", "source": "RecSys_KT"}), 0.95),
            (Document(page_content="프리미엄 가족 결합: 모바일+인터넷 결합 시, 인터넷 최대 5,500원 할인 + 모바일 월정액의 최대 50% 할인 (2회선 이상 결합 시).", 
                      metadata={"category": "marketing", "title": "프리미엄 가족 결합", "source": "RuleEngine_KT"}), 0.94),
            
            # 2. 해지 방어 (Retention - KT)
            (Document(page_content="장기 혜택 쿠폰: 2년 이상 이용 시 데이터 2GB 쿠폰 4매 제공. 시즌(Seezn) 포인트 지급.", 
                      metadata={"category": "guideline", "title": "장기 고객 혜택", "source": "Retention_Manual"}), 0.92),
            (Document(page_content="해지 방어 스크립트: '고객님, 지금 해지하시면 할인반환금이 XX원 발생하며, 결합 할인이 해지됩니다. 대신 요금제를 5G 슬림으로 하향 조정해 드릴까요?'", 
                      metadata={"category": "guideline", "title": "해지 방어 스크립트", "source": "Retention_Manual"}), 0.91),

            # 3. 약관/정책 (Terms - KT)
            (Document(page_content="선택약정 위약금(할인반환금) 산정 방식: 약정 기간 중 할인받은 금액의 일부를 반환해야 합니다. (잔여 기간 6개월 미만 시 추가 할인반환금 없음)", 
                      metadata={"category": "terms", "title": "선택약정 할인반환금", "source": "Terms_KT"}), 0.90),
            (Document(page_content="번호이동 철회: 개통 14일 이내 통화 품질 불량 확인서 지참 시, 대리점에서 철회 가능 (단말기 상태 확인 필요).", 
                      metadata={"category": "terms", "title": "번호이동 철회", "source": "Terms_KT"}), 0.89),
                      
            # 4. 기타/일반 문의 - KT
            (Document(page_content="멤버십 영화 예매: KT 멤버십 앱 > 보관함/이용권 > 영화 예매 (VIP/VVIP: 롯데시네마 무료 예매 월 1회, 연 6회 제공)", 
                      metadata={"category": "guideline", "title": "멤버십 영화 예매", "source": "CS_Manual_KT"}), 0.85),
        ]
        
        # 쿼리가 "해지"나 "위약금"을 포함하면 관련 문서 우선 반환 (간단한 키워드 매칭 시늉)
        if "해지" in query or "불편" in query:
            return [d for d in mock_docs if d[0].metadata.get("category") == "guideline" or d[0].metadata.get("category") == "terms"][:k]
        
        return mock_docs[:k]

    async def asimilarity_search(self, query: str, k: int = 4, filter: Any = None) -> List[Document]:
        # GUIDANCE 에이전트용 더미 데이터
        return [
            Document(page_content="5G 프리미어 요금제는 데이터 무제한입니다.", metadata={"category": "marketing"}),
            Document(page_content="가족 결합 할인은 최대 5명까지 가능합니다.", metadata={"category": "marketing"}),
        ]

# 실제 로딩 로직을 주석 처리하거나 우회
_vector_store = MockQdrantVectorStore()

print("Warning: Qdrant Mock Mode Activated (Memory Save)")

def get_vector_store():
    return _vector_store