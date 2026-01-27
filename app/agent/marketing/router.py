import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import os
import json
from openai import AsyncOpenAI

@dataclass
class SafetyResult:
    is_safe: bool
    reason: str
    risk_level: str  # "safe", "caution", "block"

class Gatekeeper:
    """
    The First Line of Defense.
    Filters out unsafe, angry, or irrelevant contexts BEFORE invoking the LLM.
    """
    def __init__(self):
        # 1. Emotion Blacklist (Regex for speed)
        self.furious_keywords = [
            r"개새끼", r"미친", r"씨발", r"닥쳐", r"장난해", 
            r"팀장", r"상급자", r"책임자", r"소보원", r"고발", r"신고",
            r"말귀", r"몇 번을 말해", r"안 산다"
        ]
        self.furious_pattern = re.compile("|".join(self.furious_keywords), re.IGNORECASE)

        # 2. Topic Blacklist (Sensitive contexts)
        self.sensitive_keywords = [
            r"사망", r"별세", r"장례", r"독촉", r"압류", r"파산", 
            r"소송", r"법적", r"경찰", r"병원", r"응급실"
        ]
        self.sensitive_pattern = re.compile("|".join(self.sensitive_keywords), re.IGNORECASE)

        # 3. Whitelist (High Potential)
        self.opportunity_keywords = [
            r"요금", r"할인", r"약정", r"만료", r"바꾸", r"변경", 
            r"인터넷", r"데이터", r"부족"
        ]
        self.opportunity_pattern = re.compile("|".join(self.opportunity_keywords), re.IGNORECASE)

        # [NEW] Tier 2: Fast LLM Client
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        # Ensure we have a client. If env is missing, logic checks will fail gracefully or use regex.
        if api_key:
            self.fast_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.fast_client = None
        
        # Fast Model Name
        self.fast_model = "gpt-4o-mini" # or "gpt-3.5-turbo"

    async def check_safety(self, text: str) -> SafetyResult:
        """
        Determines if the input is safe to proceed with marketing.
        Returns: SafetyResult
        """
        if not text:
            return SafetyResult(True, "Empty text", "safe")

        # Check Furious/Abusive
        if self.furious_pattern.search(text):
            return SafetyResult(False, "Detected abusive/furious language", "block")

        # Check Sensitive Topics
        if self.sensitive_pattern.search(text):
            return SafetyResult(False, "Detected sensitive topic (legal/health/death)", "block")

        return SafetyResult(True, "Passed regex filters", "safe")

    async def classify_topic(self, text: str) -> str:
        """
        Classifies the intent into: 'complaint', 'marketing', 'support', 'neutral'
        For Tier 1, we use Regex. For Tier 2, we would use an sLLM here.
        """
        if self.furious_pattern.search(text):
            return "complaint"
        
        if self.opportunity_pattern.search(text):
            return "marketing"
            
        return "neutral"

    async def semantic_route(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        [Tier 2] Fast LLM Classification.
        Returns generic JSON: {"intent": "...", "sentiment": "...", "marketing_opportunity": bool}
        """
        # 1. Fallback to Regex if client missing
        if not self.fast_client:
            topic = await self.classify_topic(text)
            return {
                "intent": topic, 
                "sentiment": "neutral", 
                "marketing_opportunity": (topic == "marketing")
            }

        # 2. Fast LLM Call
        try:
            prompt = (
                f"Analyze this customer call transcript. Extract JSON: {{'intent': 'marketing'|'support'|'complaint'|'neutral', "
                f"'sentiment': 'positive'|'neutral'|'negative'|'furious', 'marketing_opportunity': boolean}}.\n"
                f"Previous System Turn: \"{context}\"\n"
                f"Customer Input: \"{text}\"\n"
                f"CRITICAL RULES:\n"
                f"1. If customer complains about slow speed, high bill, or lack of data, set 'marketing_opportunity': true (Upsell chance).\n"
                f"2. If customer asks a Follow-up Question about a previous proposal (e.g., 'What is it?', 'How much?'), set 'marketing_opportunity': true.\n"
                f"3. Only set 'marketing_opportunity': false if it is a pure technical crash or furious legal threat."
            )
            print("[Router] 🚀 Sending request to gpt-4o-mini...")
            import time
            t0 = time.time()
            completion = await self.fast_client.chat.completions.create(
                model=self.fast_model,
                messages=[{"role": "system", "content": "You are a JSON classifier."}, {"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
                response_format={"type": "json_object"}
            )
            print(f"[Router] ✅ Received response in {time.time()-t0:.2f}s")
            content = completion.choices[0].message.content.strip()
            # Loose JSON parsing (handle potential markdown fences)
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            return json.loads(content)
        except Exception as e:
            print(f"[Router] Fast LLM failed: {e}")
            # Fallback to Regex
            topic = await self.classify_topic(text)
            return {
                "intent": topic, 
                "sentiment": "unknown", 
                "marketing_opportunity": (topic == "marketing")
            }

    async def should_skip_marketing(self, text: str) -> bool:
        """
        Quick check for MarketingSession.
        """
        safety = await self.check_safety(text)
        if not safety.is_safe:
            return True
        return False
