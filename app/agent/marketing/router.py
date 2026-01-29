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
            r"개새끼", r"미친", r"씨발", r"닥쳐", r"장난해", r"임마", r"자식", r"새끼", r"꺼져",
            r"팀장", r"상급자", r"책임자", r"소보원", r"고발", r"신고",
            r"말귀", r"몇 번을 말해", r"안 산다", r"짜증"
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
            r"인터넷", r"데이터", r"부족", r"느려", r"답답", r"비싸",
            r"해지", r"탈퇴", r"그만", r"끊어", r"다른"
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

        # 2. [Optimization] Zero-Cost Heuristic Checks (Save API Cost)
        
        # 2-0. Regex Classification (Priority 1)
        # Check explicit markers FIRST.
        regex_topic = await self.classify_topic(text)
        if regex_topic == "complaint":
             print(f"[Router] ⏩ Skip: Detected complaint/insult via Regex ('{text}')")
             return {"intent": "complaint", "marketing_opportunity": False}
        if regex_topic == "marketing":
             # If explicit marketing keyword is present, proceed to LLM for detail, OR return True immediately?
             # For now, let's allow LLM to decide strategy if keyword is found.
             pass

        # 2-1. Length Check (Short & No Keyword)
        # If < 6 chars and NO marketing keyword -> Skip.
        # "야 임마"(5) -> No marketing key -> Skip.
        # "데이터"(3) -> Marketing key -> Pass.
        if len(text) < 6 and regex_topic != "marketing":
            print(f"[Router] ⏩ Skip: Text too short & no trigger ('{text}')")
            return {"intent": "neutral", "marketing_opportunity": False}

        # 2-3. Safety Check
        is_safe_result = await self.check_safety(text)
        if not is_safe_result.is_safe:
             print("[Router] ⏩ Skip: Unsafe content")
             return {"intent": "unsafe", "marketing_opportunity": False}

        # 3. Fast LLM Call (Only for ambiguous cases)
        try:
            prompt = (
                f"Analyze this customer call transcript. Extract JSON: {{'intent': 'marketing'|'support'|'complaint'|'neutral', "
                f"'sentiment': 'positive'|'neutral'|'negative'|'furious', 'marketing_opportunity': boolean}}.\n"
                f"Previous System Turn: \"{context}\"\n"
                f"Customer Input: \"{text}\"\n"
                f"CRITICAL RULES (Sniper Mode):\n"
                f"0. [RETENTION] If user mentions 'Cancel', 'Terminate', 'Unsubscribe' (해지, 탈퇴) -> SET 'marketing_opportunity': true (Retention Opportunity).\n"
                f"1. [SOLVER] If complaint is about 'Price', 'Data Cap', or 'Slow Speed' (that can be fixed by plan upgrade) -> SET 'marketing_opportunity': true.\n"
                f"2. [RESOLUTION] If customer says 'Fixed', 'Thanks', ' Solved' -> SET 'marketing_opportunity': true (Post-resolution Offer).\n"
                f"3. [SKIP] If problem is purely technical (Device broken, No Signal, WiFi setting, Login failed) AND not resolved yet -> SET 'marketing_opportunity': false.\n"
                f"4. [SKIP] If customer is FURIOUS -> SET 'marketing_opportunity': false.\n"
                f"5. [INQUIRY] If customer asks about 'Plans', 'Discounts', 'Benefits', 'Join' (가입, 결합, 할인) -> SET 'marketing_opportunity': true."
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
