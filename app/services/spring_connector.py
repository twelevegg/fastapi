import httpx
import logging
import os
from app.core.config import settings
from app.schemas.customer import CustomerInfo

logger = logging.getLogger(__name__)

class SpringConnector:
    def __init__(self):
         # 실제 운영 환경에서는 환경변수로 관리
         # .env에서 읽어오거나 기본값 사용
        self.spring_api_url = os.getenv("SPRING_API_URL", "http://localhost:8080/api/v1/calls/end")
        self.customer_api_url_base = os.getenv("SPRING_CUSTOMER_API_URL", "http://localhost:8080/api/v1/customers/search")
        self.api_key = os.getenv("SPRING_API_KEY")

    async def get_customer_info(self, customer_number: str) -> CustomerInfo:
        """
        Spring 서버에서 고객 정보를 조회합니다.
        
        Args:
            customer_number (str): 고객 전화번호 (또는 식별자)
        
        Returns:
            CustomerInfo: 고객 정보 객체 (실패 시 None 또는 예외 발생)
        """
        try:
            # Spring Controller: @GetMapping("/search") @RequestParam String phoneNumber
            # URL: .../search
            # Params: { "phoneNumber": "..." }
            url = self.customer_api_url_base
            params = {"phoneNumber": customer_number}
            headers = {"X-API-KEY": self.api_key} if self.api_key else {}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=5.0)
                if response.status_code == 404:
                    logger.warning(f"Customer not found: {customer_number}")
                    return None
                    
                response.raise_for_status()
                data = response.json()
                # Pydantic 모델로 변환 (alias를 사용하여 매핑)
                return CustomerInfo(**data)
                
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP error fetching customer info: {e.response.text}")
             return None
        except Exception as e:
            logger.error(f"Failed to fetch customer info: {e}")
            return None

    async def send_call_data(self, call_data: dict):
        """
        상담 종료 후 데이터를 Spring 서버로 전송합니다.
        
        Args:
            call_data (dict): {
                "transcripts": [ ... ],
                "summary": "...",
                ...
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {"X-API-KEY": self.api_key} if self.api_key else {}
                response = await client.post(
                    self.spring_api_url, 
                    json=call_data,
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"Successfully sent call data to Spring: {response.status_code}")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending data to Spring: {e.response.text}")
        except Exception as e:
            logger.error(f"Failed to send call data to Spring: {e}")

spring_connector = SpringConnector()
