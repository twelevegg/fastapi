from pydantic import BaseModel, Field
from typing import Optional

class CustomerInfo(BaseModel):
    customer_id: str = Field(..., alias="고객 ID")
    name: str = Field(..., alias="이름")
    gender: Optional[str] = Field(None, alias="성별")
    age: Optional[int] = Field(None, alias="나이")
    phone_number: str = Field(..., alias="전화번호")
    is_foreigner: Optional[str] = Field(None, alias="외국인 유무(Y/N)")
    combination_product: Optional[str] = Field(None, alias="결합상품명")
    rate_plan: Optional[str] = Field(None, alias="요금제명")
    iptv_product: Optional[str] = Field(None, alias="IPTV 상품 명")
    contract_period: Optional[str] = Field(None, alias="약정기간")
    remaining_months: Optional[str] = Field(None, alias="잔여개월")
    optional_contract: Optional[str] = Field(None, alias="선택약정(Y/N)")
    internet_product: Optional[str] = Field(None, alias="인터넷상품명")
    welfare_card: Optional[str] = Field(None, alias="복지카드(Y/N)")
    overcharge_1_month_ago: Optional[str] = Field(None, alias="초과 요금 발생 여부(1개월 전)")
    overcharge_2_months_ago: Optional[str] = Field(None, alias="초과 요금 발생 여부(2개월 전)")
    data_carryover: Optional[str] = Field(None, alias="데이터 이월 여부(Y/N)")
    data_sharing: Optional[str] = Field(None, alias="쉐어링 사용 여부(Y/N)")
    household_type: Optional[str] = Field(None, alias="1인가구/가족 가구")
    remote_work: Optional[str] = Field(None, alias="재택 근무")

    class Config:
        allow_population_by_field_name = True
