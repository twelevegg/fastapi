from typing import Dict, Any, Optional
from collections import OrderedDict
import time
import re
import asyncio

class SemanticCache:
    """
    Tier 1.5 Cache (LRU).
    반복되는 질문(예: "요금제 변경해줘")에 대한 분석 결과를 메모리에 저장하여
    LLM 호출 비용과 시간을 절약합니다.
    """
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def _normalize_key(self, text: str) -> str:
        """
        Hit율을 높이기 위해 텍스트 정규화.
        - 공백/특수문자 제거, 소문자 변환.
        """
        text = re.sub(r"[^\w]", "", text)
        return text.lower()

    async def get(self, text: str) -> Optional[Dict[str, Any]]:
        key = self._normalize_key(text)
        if key in self._cache:
            self._hits += 1
            # LRU: 최근 사용된 항목을 뒤로 이동 (Move to End)
            self._cache.move_to_end(key)
            print(f"[Cache] HIT for '{text}' (key: {key})")
            return self._cache[key]
        self._misses += 1
        return None

    async def set(self, text: str, value: Dict[str, Any]):
        key = self._normalize_key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        
        # Max Size 초과 시 오래된 항목(앞쪽) 제거
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
