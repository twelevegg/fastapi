CAUSE_MAP = [
    {
        "keywords": ["데이터", "사용량", "영상"],
        "type": "usage_overage",
        "category": "data",
    },
    {
        "keywords": ["통화", "전화"],
        "type": "usage_overage",
        "category": "voice",
    },
    {
        "keywords": ["문자", "sms"],
        "type": "usage_overage",
        "category": "sms",
    },
    {
        "keywords": ["소액결제", "휴대폰 결제"],
        "type": "payment",
        "category": "mobile_payment",
    },
    {
        "keywords": ["콘텐츠", "앱 결제"],
        "type": "payment",
        "category": "content",
    },
    {
        "keywords": ["부가서비스", "자동"],
        "type": "addon_service",
        "category": "subscription",
    },
]

def map_cause(cause_text: str):
    for rule in CAUSE_MAP:
        if any(k in cause_text for k in rule["keywords"]):
            return {
                "type": rule["type"],
                "category": rule["category"],
            }
    return None
