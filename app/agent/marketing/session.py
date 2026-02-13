\
import os
import re
import json
import time
import glob
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import numpy as np

import httpx

from qdrant_client import QdrantClient, models
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from app.agent.marketing.prompts import (
    BASE_SYSTEM, STRATEGY_UPSELL, STRATEGY_RETENTION, STRATEGY_DEFAULT
)

# -------------------------
# Safety: PII masking
# -------------------------

def mask_pii(text: str) -> str:
    if not text:
        return ""
        
    # [Patch] Handle Dict (Structured Agent Script)
    if isinstance(text, dict):
        text = text.get("ment") or text.get("recommendation") or str(text)
        
    t = str(text) # Ensure string
    t = re.sub(r"\b01[0-9][- ]?\d{3,4}[- ]?\d{4}\b", "<PHONE>", t)
    t = re.sub(r"\b\d{6,}\b", "<NUM>", t)
    t = re.sub(r"([가-힣]{1,10}(?:로|길)\s*\d+(?:[가-힣0-9\s\-]*)?)", "<ADDRESS>", t)
    t = re.sub(r"\b\d+\s*호\b", "<HO>", t)
    t = re.sub(r"(성함이)\s*([가-힣]{2,4})", r"\1 <NAME>", t)
    t = re.sub(r"(상담사)\s*([가-힣]{2,4})", r"\1 <NAME>", t)
    t = re.sub(r"([가-힣]{2,4})\s*고객님", r"<NAME> 고객님", t)
    return t

import math

def safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x)

def parse_first_won(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원", text)
    if not m:
        m = re.search(r"([0-9]+)\s*원", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


# -------------------------
# Customer DB
# -------------------------

@dataclass
class CustomerProfile:
    customer_id: str = ""
    phone: str = ""
    subscription_type: str = ""
    mobile_plan: str = ""
    iptv_plan: str = ""
    internet_plan: str = ""
    monthly_fee_won: Optional[int] = None
    contract_active: Optional[bool] = None
    contract_months: Optional[int] = None
    contract_remaining_months: Optional[int] = None
    discount_status: str = ""
    addons: str = ""
    overage_1m: str = ""
    overage_2m: str = ""
    data_share: str = ""
    roaming_history: str = ""
    region: str = ""
    household: str = ""
    remote_work: str = ""
    segment_guess: str = ""
    signals: List[str] = field(default_factory=list)

    def to_prompt_json(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "subscription_type": self.subscription_type,
            "mobile_plan": self.mobile_plan,
            "internet_plan": self.internet_plan,
            "iptv_plan": self.iptv_plan,
            "monthly_fee_won": self.monthly_fee_won,
            "contract": {
                "active": self.contract_active,
                "months": self.contract_months,
                "remaining_months": self.contract_remaining_months,
            },
            "discount_status": self.discount_status,
            "addons": self.addons,
            "overage": {"1m_ago": self.overage_1m, "2m_ago": self.overage_2m},
            "data_share": self.data_share,
            "roaming_history": self.roaming_history,
            "region": self.region,
            "household": self.household,
            "remote_work": self.remote_work,
            "segment_guess": self.segment_guess,
            "signals": self.signals,
        }


    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CustomerProfile":
        """
        Create CustomerProfile from a dictionary (e.g. from agent API mock data)
        """
        # Helper for safe string conversion
        def s(k): return safe_str(data.get(k))
        # Helper for safe int
        def i(k): 
            val = data.get(k)
            return int(val) if val and str(val).isdigit() else None
        
        # MAPPING: agent.py mock data keys -> CustomerProfile fields
        # agent.py sends: {"customer_id", "name", "rate_plan", "joined_date"} usually
        # But we might want more enriched data if possible.
        # For now, we map what we can.
        
        prof = CustomerProfile(
            customer_id=s("customer_id"),
            phone=s("phone") or s("contact") or s("phone_number"),
            subscription_type=s("subscription_type"),
            mobile_plan=s("rate_plan") or s("mobile_plan") or s("요금제명"), # Map 'rate_plan' from agent.py
            iptv_plan=s("iptv_plan"),
            internet_plan=s("internet_plan"),
            monthly_fee_won=i("monthly_fee_won"),
            contract_active=True, # Default to True for safety if unknown
            contract_months=i("contract_months"),
            contract_remaining_months=i("contract_remaining_months"),
            discount_status=s("discount_status"),
            addons=s("addons"),
            overage_1m=s("overage_1m"),
            overage_2m=s("overage_2m"),
            data_share=s("data_share"),
            roaming_history=s("roaming_history"),
            region=s("region"),
            household=s("household"),
            remote_work=s("remote_work"),
            segment_guess=s("segment_guess"),
        )
        # Signals might be pre-calculated or needs to be derived
        # If data doesn't have detailed fields, _derive_signals might be weak, but that's expected with mock data.
        prof.signals = CustomerDB._derive_signals(prof)
        return prof

class CustomerDB:
    # Legacy container for helper methods
    
    @staticmethod
    def _derive_signals(p: CustomerProfile) -> List[str]:
        s = []
        # 1. Contract Analysis
        if p.contract_remaining_months is not None:
            if p.contract_remaining_months <= 1:
                s.append("약정 만료 임박(D-30: 즉시 재약정 유도)")
            elif p.contract_remaining_months <= 3:
                s.append("약정 종료 예정(D-90: 선제적 방어/요금제 상향 제안)")
                
        # 2. Overage (Pain Point)
        if (p.overage_1m or "").upper() == "Y" or (p.overage_2m or "").upper() == "Y":
            s.append("초과요금 발생(요금제 상향 1순위 타겟)")
            
        # 3. Usage Pattern (Roaming, Discount, Internet)
        if p.roaming_history and "없음" not in p.roaming_history:
            s.append("로밍 이력 보유(해외 여행/로밍 상품 관심)")
        if p.discount_status and "미적용" in p.discount_status:
            s.append("할인 미적용(결합/약정 할인 미끼로 설득 가능)")
        if p.internet_plan:
            s.append("인터넷 사용중(유무선 결합 유지/혜택 강조)")
        else:
            s.append("인터넷 미사용(인터넷 결합상품 크로스셀링 기회)")
            
        # 4. Household & Segment
        if p.household and "가족" in p.household:
            s.append("가족 세대(패밀리 요금제/결합할인 소구)")
        if p.segment_guess and "학생" in p.segment_guess:
            s.append("학생/청소년(데이터 무제한보다는 가성비/공유 혜택)")
            
        # 5. ARPU (Spending Power) - NEW
        if p.monthly_fee_won:
            if p.monthly_fee_won >= 80000:
                s.append("고액 요금 납부자(VIP: 멤버십/프리미엄 혜택 강조하여 이탈 방어)")
            elif p.monthly_fee_won <= 35000:
                s.append("저액 요금 납부자(ARPU 증대 필요: 1~2만원 추가 업셀링 시도)")
                
        # 6. Data Sharing
        if p.data_share and "사용" in p.data_share:
            s.append("데이터 쉐어링 이용(멀티 디바이스 유저 -> 워치/태블릿 결합 제안)")
            
        return s

# -------------------------
# Qdrant retrieval (semantic + keyword + hybrid + staged category)
# -------------------------

@dataclass(frozen=True)
class RetrievedItem:
    doc_id: str
    score: float
    page_content: str
    metadata: Dict[str, Any]
    category: str

def _normalize_doc_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    if "metadata" in meta and isinstance(meta["metadata"], dict):
        inner = meta["metadata"]
        if any(k in inner for k in ["source", "title", "category"]):
            return inner
    return meta

class QdrantSearchEngine:
    def __init__(
        self,
        client: QdrantClient,
        collection: str = "cs_guideline",
        vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
        category_key: str = "metadata.category",
    ):
        self.client = client
        self.collection = collection
        self.vector_name = vector_name
        self.sparse_vector_name = sparse_vector_name
        self.category_key = category_key

        self.dense_embeddings = FastEmbedEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            normalize=True,
        )
        self.sparse_embeddings = FastEmbedSparse(
            model_name="Qdrant/bm25",
            sparse=True,
        )

        self.vs_dense = QdrantVectorStore(
            client=client,
            collection_name=collection,
            embedding=self.dense_embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.DENSE,
            vector_name=vector_name,
            sparse_vector_name=sparse_vector_name,
        )
        self.vs_sparse = QdrantVectorStore(
            client=client,
            collection_name=collection,
            embedding=self.dense_embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.SPARSE,
            vector_name=vector_name,
            sparse_vector_name=sparse_vector_name,
        )
        self.vs_hybrid = QdrantVectorStore(
            client=client,
            collection_name=collection,
            embedding=self.dense_embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name=vector_name,
            sparse_vector_name=sparse_vector_name,
        )

        # sample existing categories so staged search doesn't filter by non-existent values
        self.existing_categories = self._sample_categories(250)

    def _sample_categories(self, n: int = 250) -> List[str]:
        cats = set()
        pts, _ = self.client.scroll(
            collection_name=self.collection,
            limit=n,
            with_payload=True,
            with_vectors=False,
        )
        for p in pts:
            md = (p.payload or {}).get("metadata", {})
            if isinstance(md, dict) and md.get("category"):
                cats.add(md["category"])
        return sorted(cats)

    async def prefetch(self, trigger_chunk: str) -> None:
        """
        [Speculative Execution] 
        Runs Qdrant search in background when a trigger is detected in a fragment.
        """
        print(f"[Session] Prefetching for trigger: '{trigger_chunk}'")
        # Build a temporary query around the trigger
        # In reality, we might want more context, but trigger itself is a strong signal
        query = f"Prefetch: {trigger_chunk}"
        # Execute search (simplified parameters for speed)
        cats = ["marketing", "terms"]
        q_items = await self.staged_category_search(query=trigger_chunk, final_k=5, categories=cats)
        
        # Store result
        self._prefetch_cache = {
            "query": trigger_chunk,
            "items": q_items,
            "timestamp": time.time()
        }

    def dialogue_text(self, last_n: int = 14) -> str:
        part = self.turns[-last_n:] if last_n and len(self.turns) > last_n else self.turns
        lines = []
        for t in part:
            role = "고객" if t.speaker == "customer" else "상담원"
            txt = mask_pii(t.transcript or "")
            if txt.strip():
                lines.append(f"{role}: {txt}")
        return "\n".join(lines).strip()

    def build_query(self) -> str:
        dialog = self.dialogue_text()
        
        # [Context Optimization] Extract Product Names from recent dialogue
        # Specifically, check the LAST turn (Agent or Customer) for mentions of ANY known product.
        recent_mentions = []
        last_turn_text = ""
        if self.turns:
            # Check last 2 turns (User + Agent)
            for t in self.turns[-2:]:
                if t.transcript and isinstance(t.transcript, str):
                   last_turn_text += " " + t.transcript

        # Simple keyword extraction (just for query weighting)
        return dialog[-400:] # Naive implementation

    def _filter(self, category: Optional[str]) -> Optional[models.Filter]:
        if not category:
            return None
        return models.Filter(
            must=[models.FieldCondition(key=self.category_key, match=models.MatchValue(value=category))]
        )

    def _to_items(self, pairs: List[Tuple[Document, float]]) -> List[RetrievedItem]:
        out = []
        for i, (doc, score) in enumerate(pairs, start=1):
            meta = _normalize_doc_metadata(doc.metadata or {})
            out.append(
                RetrievedItem(
                    doc_id=f"DOC{i}",
                    score=float(score),
                    page_content=doc.page_content or "",
                    metadata=meta,
                    category=safe_str(meta.get("category")),
                )
            )
        return out

    async def semantic(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(await self.vs_dense.asimilarity_search_with_score(query=query, k=k, filter=self._filter(category)))

    async def keyword(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(await self.vs_sparse.asimilarity_search_with_score(query=query, k=k, filter=self._filter(category)))

    async def hybrid(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(await self.vs_hybrid.asimilarity_search_with_score(query=query, k=k, filter=self._filter(category)))

    @staticmethod
    def _rrf(lists: List[List[RetrievedItem]], weights: List[float], final_k: int = 10, rrf_k: int = 60) -> List[RetrievedItem]:
        def uid(it: RetrievedItem) -> str:
            src = safe_str(it.metadata.get("source"))
            title = safe_str(it.metadata.get("title"))
            head = (it.page_content or "")[:120]
            return f"{src}||{title}||{head}"

        fused = defaultdict(float)
        best = {}
        for w, items in zip(weights, lists):
            for rank, it in enumerate(items, start=1):
                u = uid(it)
                fused[u] += float(w) / (rrf_k + rank)
                if (u not in best) or (it.score > best[u].score):
                    best[u] = it

        ranked = sorted(fused.keys(), key=lambda u: fused[u], reverse=True)
        out = []
        for i, u in enumerate(ranked[:final_k], start=1):
            it = best[u]
            out.append(RetrievedItem(doc_id=f"DOC{i}", score=it.score, page_content=it.page_content, metadata=it.metadata, category=it.category))
        return out

    async def fused_search(self, query: str, final_k: int = 10, k_each: int = 8, category: Optional[str] = None) -> List[RetrievedItem]:
        sem = await self.semantic(query, k=k_each, category=category)
        kw = await self.keyword(query, k=k_each, category=category)
        hy = await self.hybrid(query, k=k_each, category=category)
        return self._rrf([sem, kw, hy], [1.0, 1.0, 1.2], final_k=final_k)

    async def staged_category_search(
        self,
        query: str,
        final_k: int = 10,
        per_category_k: int = 6,
        categories: Optional[List[str]] = None,
        cat_weights: Optional[Dict[str, float]] = None,
        always_include: Optional[Dict[str, int]] = None,
    ) -> List[RetrievedItem]:
        categories = categories or ["marketing", "guideline", "principle", "terms"]
        cat_weights = cat_weights or {"marketing": 1.45, "guideline": 1.15, "principle": 1.05, "terms": 1.0}
        always_include = always_include or {"terms": 2}

        cats = [c for c in categories if c in self.existing_categories]
        if not cats:
            return await self.fused_search(query, final_k=final_k, k_each=max(per_category_k, 6), category=None)

        per = []
        ws = []
        for c in cats:
            per.append(await self.fused_search(query, final_k=per_category_k, k_each=per_category_k, category=c))
            ws.append(float(cat_weights.get(c, 1.0)))

        merged = self._rrf(per, ws, final_k=max(final_k, sum(always_include.values())))

        def uid(it: RetrievedItem) -> str:
            return f"{safe_str(it.metadata.get('source'))}||{safe_str(it.metadata.get('title'))}||{(it.page_content or '')[:120]}"

        # enforce minimum terms etc
        forced = []
        seen_u = set()
        for cat, n in always_include.items():
            if cat not in self.existing_categories:
                continue
            for it in [x for x in merged if x.category == cat][: int(n)]:
                u = uid(it)
                if u not in seen_u:
                    forced.append(it)
                    seen_u.add(u)

        final, seen = [], set()
        for it in forced + merged:
            u = uid(it)
            if u in seen:
                continue
            final.append(it)
            seen.add(u)
            if len(final) >= final_k:
                break

        out = []
        for i, it in enumerate(final, start=1):
            out.append(RetrievedItem(doc_id=f"DOC{i}", score=it.score, page_content=it.page_content, metadata=it.metadata, category=it.category))
        return out

def build_context(items: List[RetrievedItem], max_chars: int = 8500, per_doc_chars: int = 850) -> Tuple[str, List[Dict[str, Any]]]:
    blocks, ev, used = [], [], 0
    for it in items:
        src = safe_str(it.metadata.get("source"))
        title = safe_str(it.metadata.get("title"))
        cat = safe_str(it.category)
        txt = re.sub(r"\n{3,}", "\n\n", (it.page_content or "").strip())[:per_doc_chars]
        block = f"[{it.doc_id}]\n- category: {cat}\n- title: {title}\n- source: {src}\n- content:\n{txt}\n"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
        ev.append({"doc_id": it.doc_id, "category": cat, "title": title, "source": src, "excerpt": txt[:240], "score": it.score})
    return "\n\n".join(blocks).strip(), ev


# -------------------------
# Router (fast gating)
# -------------------------

def quick_router(dialogue: str, customer: CustomerProfile) -> Dict[str, Any]:
    t = dialogue or ""
    reasons = []

    stage = "unknown"
    if any(k in t for k in ["성함", "본인", "명의", "인증", "주소지", "연락주신 번호", "확인"]):
        stage = "verification"
        reasons.append("본인확인/정보확인 발화 감지")
    if any(k in t for k in ["동의", "녹취", "개인정보", "위탁", "보관", "약관", "필수적으로 필요"]):
        stage = "consent"
        reasons.append("동의/고지/약관 발화 감지")
    if any(k in t for k in ["감사", "좋은 하루", "행복한 하루", "상담사", "종료"]):
        stage = "closing"
        reasons.append("마무리/종결 발화 감지")

    churn_words = ["해지", "해약", "번호이동", "옮기", "탈퇴"]
    upsell_words = ["요금제", "변경", "업그레이드", "추가", "부가서비스", "데이터", "무제한", "결합", "가족결합", "재결합", "할인", "혜택"]

    churn = any(w in t for w in churn_words)
    upsell = any(w in t for w in upsell_words)

    db_signal = any(any(k in s for k in ["약정 만료", "초과요금", "할인 미적용", "결합"]) for s in customer.signals) if customer.signals else False

    marketing_needed = False
    mtype = "none"

    if churn:
        marketing_needed = True
        mtype = "retention"
        reasons.append("해지/이탈 의사 키워드 감지")
    elif upsell or db_signal:
        marketing_needed = True
        mtype = "upsell"
        reasons.append("요금제/결합/혜택 키워드 또는 DB 신호 감지")

    complaint = any(w in t for w in ["불만", "끊김", "느려", "장애", "환불", "오류", "안돼", "문제"])
    if complaint and marketing_needed:
        mtype = "hybrid"
        reasons.append("불만/문제 해결 이후 제안이 필요한 상황으로 추정")

    # gate in verification/consent unless customer explicitly requested plan/bundle/discount
    if stage in ["verification", "consent"] and not churn:
        if upsell:
            reasons.append("verification/consent 단계지만 고객이 결합/요금제 흐름 → 제한적 안내 가능")
        else:
            marketing_needed = False
            mtype = "support_only"
            reasons.append("verification/consent 단계에서 마케팅 보류")

    return {"call_stage_hint": stage, "marketing_needed_hint": marketing_needed, "marketing_type_hint": mtype, "reasons": reasons[:6]}


# Prompts are now imported from app.agent.marketing.prompts


# -------------------------
# LLM client (OpenAI-compatible) using httpx (no requests pin)
# -------------------------

class OpenAICompatibleLLM:
    def __init__(self, timeout: int = 60):
        self.base_url = (os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        self.timeout = timeout

        # Optional: allow fallback when response_format is not supported by the upstream.
        # Default is strict (no fallback) to avoid non-JSON outputs.
        self.allow_fallback = (os.environ.get("LLM_ALLOW_FALLBACK") or "").strip().lower() in ["1", "true", "yes", "y"]

        if not self.base_url or not self.api_key or not self.model:
            raise RuntimeError("LLM env missing: LLM_BASE_URL/LLM_API_KEY/LLM_MODEL (or OPENAI_*)")

    def _strip_code_fences(self, text: str) -> str:
        t = (text or "").strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
            t = re.sub(r"\s*```\s*$", "", t)
        return t.strip()

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = self._strip_code_fences((text or "").strip())

        # 1) direct parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2) substring between first { and last }
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e != -1 and e > s:
            chunk = text[s:e+1]
            try:
                return json.loads(chunk)
            except Exception:
                # 3) optional repair (best-effort)
                try:
                    from json_repair import repair_json  # optional dependency
                    repaired = repair_json(chunk)
                    return json.loads(repaired)
                except Exception:
                    pass

        raise ValueError("JSON parse failed")

    async def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 1400) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        # Prefer JSON Mode
        payload = dict(base_payload)
        payload["response_format"] = {"type": "json_object"}

        async def _post(cx: httpx.AsyncClient, pl: Dict[str, Any]) -> httpx.Response:
            return await cx.post(f"{self.base_url}/chat/completions", headers=headers, json=pl)

        async with httpx.AsyncClient(timeout=self.timeout) as cx:
            r = await _post(cx, payload)

            # If JSON mode is rejected (often 400), optionally fallback if user allowed it.
            if r.status_code >= 400:
                if self.allow_fallback:
                    r = await _post(cx, base_payload)
                else:
                    print("HTTP", r.status_code)
                    print(r.text)
                    raise RuntimeError(
                        "LLM이 JSON 응답 모드(response_format=json_object)를 거절했습니다. "
                        "LLM_MODEL을 JSON 모드를 지원하는 모델로 설정하세요(예: gpt-4o-mini). "
                        "또는 LLM_ALLOW_FALLBACK=1로 fallback을 허용할 수 있습니다(비권장)."
                    )

            try:
                r.raise_for_status()
            except Exception:
                print("HTTP", r.status_code)
                print(r.text)
                raise

            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            finish_reason = choice.get("finish_reason")
            content = (((choice.get("message") or {}).get("content")) or "").strip()

            # If truncated by token limit, retry once with stronger compactness instruction (still JSON Mode).
            if finish_reason == "length":
                compact_instr = (
                    "직전 출력이 길이 제한으로 잘렸다. 스키마/키 구조는 절대 바꾸지 말고, "
                    "각 문자열/리스트를 더 짧게 요약해서 JSON 단일 객체로 다시 출력하라. "
                    "next_actions는 최대 2개, micro_branches는 최대 2개로 제한하라."
                )
                retry_payload = dict(base_payload)
                retry_payload["messages"] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + "\n\n[추가 지시]\n" + compact_instr},
                ]
                retry_payload["temperature"] = 0.0
                retry_payload["max_tokens"] = int(min(max_tokens * 2, 3200))
                retry_payload["response_format"] = {"type": "json_object"}

                r2 = await _post(cx, retry_payload)
                try:
                    r2.raise_for_status()
                except Exception:
                    print("HTTP", r2.status_code)
                    print(r2.text)
                    raise
                data2 = r2.json()
                choice2 = (data2.get("choices") or [{}])[0]
                content = (((choice2.get("message") or {}).get("content")) or "").strip()

            # Parse JSON, else repair once (still JSON Mode if possible)
            try:
                return self._extract_json(content)
            except Exception:
                repair_prompt = (
                    "직전 출력이 JSON 파싱에 실패했다. 오직 JSON 단일 객체만, 스키마 그대로 재출력하라.\n"
                    "다른 텍스트/마크다운/설명 금지.\n"
                    "문자열 내 따옴표/개행은 JSON 규칙에 맞게 이스케이프하라.\n\n"
                    f"직전 출력(일부):\n{content[:6000]}"
                )

                payload2 = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": repair_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": int(min(max_tokens * 2, 3200)),
                    "response_format": {"type": "json_object"},
                }

                r3 = await _post(cx, payload2)

                # If JSON mode is rejected here and fallback allowed, try without response_format once.
                if r3.status_code >= 400 and self.allow_fallback:
                    payload2_nf = dict(payload2)
                    payload2_nf.pop("response_format", None)
                    r3 = await _post(cx, payload2_nf)

                try:
                    r3.raise_for_status()
                except Exception:
                    print("HTTP", r3.status_code)
                    print(r3.text)
                    raise

                data3 = r3.json()
                choice3 = (data3.get("choices") or [{}])[0]
                content3 = (((choice3.get("message") or {}).get("content")) or "").strip()

                return self._extract_json(content3)


class MockLLM:

    async def chat_json(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        return {
            "call_stage": "unknown",
            "marketing_needed": False,
            "marketing_type": "support_only",
            "customer_state": {
                "sentiment": {"label": "neutral", "score": 0.5},
                "emotion_tags": ["confusion"],
                "primary_intent": "unknown",
                "churn_risk": {"level": "medium", "score": 0.5},
                "key_pain_points": ["LLM 미설정(데모)"]
            },
            "decision": {
                "why_marketing_needed_or_not": "LLM 미설정 상태로 멘트 생성 제한",
                "branch_reason": "support_only",
                "next_questions": ["요청하시는 목적(결합/요금/해지/혜택)을 확인 부탁드립니다."],
                "next_actions": [
                    {
                        "priority": 1,
                        "type": "support",
                        "goal": "요청사항 확인",
                        "rationale": "추가 정보 필요",
                        "agent_script": {
                            "opening": "고객님, 정확한 안내를 위해 몇 가지 확인드리겠습니다.",
                            "empathy": "불편을 드려 죄송합니다.",
                            "probing_questions": ["지금 결합 신청/변경이 목적이실까요?"],
                            "proposal": "확인 후 가능한 옵션을 안내드리겠습니다.",
                            "objection_handling": ["확인 절차 후 안내 가능"],
                            "closing": "확인 후 바로 도와드리겠습니다."
                        },
                        "evidence_doc_ids": [],
                        "product_ids": []
                    }
                ],
                "micro_branches": []
            },
            "policy_answer": {"answer": "근거 기반 확인 필요", "evidence_doc_ids": []},
            "product_recommendations": [],
            "needs_more_info": True,
            "missing_info": ["LLM 설정(LLM_BASE_URL/LLM_API_KEY/LLM_MODEL)"],
            "safety_and_compliance": {
                "do_not_claim": ["근거 없는 수치/프로모션/위약금 확정 안내 금지"],
                "checks_before_offer": ["약정/대상/조건 확인"],
                "risk_flags": ["LLM 미설정"]
            }
        }


# -------------------------
# Session
# -------------------------

@dataclass
class Turn:
    turn_id: int
    speaker: str
    transcript: str


from .router import Gatekeeper
from .cache import SemanticCache

class MarketingSession:
    def __init__(self, customer: CustomerProfile, qdrant: QdrantSearchEngine, llm: Any):
        self.customer = customer
        # self.product_index = product_index # Removed
        self.qdrant = qdrant

        self.llm = llm
        
        # [NEW] Gatekeeper & Cache
        self.gatekeeper = Gatekeeper()
        self.cache = SemanticCache()
        
        # [NEW] Prefetch Cache
        # Stores Qdrant results for triggers found in fragments
        self._prefetch_cache: Dict[str, Any] = None
        
        # [Context Optimization] Sticky Product Context
        self.current_proposal: Optional[List[Dict[str, Any]]] = None
        
        self.turns: List[Turn] = []
        self.state_prev = {"call_stage": "unknown", "marketing_needed": False, "marketing_type": "none"}
        self.call_stage = "unknown"

        # [NEW] LangGraph with Persistent Memory
        from app.agent.marketing.graph import build_marketing_graph
        self.graph = build_marketing_graph()

    def add_turn(self, speaker: str, transcript: str, turn_id: Optional[int] = None) -> None:
        sp = "customer" if speaker == "customer" else "agent"
        if turn_id is None:
            turn_id = (self.turns[-1].turn_id + 1) if self.turns else 1
        self.turns.append(Turn(turn_id=turn_id, speaker=sp, transcript=transcript or ""))

    async def prefetch(self, trigger_chunk: str) -> None:
        """
        [Speculative Execution] 
        Runs Qdrant search in background when a trigger is detected in a fragment.
        """
        print(f"[Session] Prefetching for trigger: '{trigger_chunk}'")
        # Build a temporary query around the trigger
        # In reality, we might want more context, but trigger itself is a strong signal
        query = f"Prefetch: {trigger_chunk}"
        # Execute search (simplified parameters for speed)
        cats = ["marketing", "terms"]
        q_items = self.qdrant.staged_category_search(query=trigger_chunk, final_k=5, categories=cats)
        
        # Store result
        self._prefetch_cache = {
            "query": trigger_chunk,
            "items": q_items,
            "timestamp": time.time()
        }
    
    def dialogue_text(self, last_n: int = 14) -> str:
        part = self.turns[-last_n:] if last_n and len(self.turns) > last_n else self.turns
        lines = []
        for t in part:
            role = "고객" if t.speaker == "customer" else "상담원"
            txt = mask_pii(t.transcript or "")
            if txt.strip():
                lines.append(f"{role}: {txt}")
        return "\n".join(lines).strip()

    def build_query(self) -> str:
        dialog = self.dialogue_text()
        
        # [Context Optimization] Extract Product Names from recent dialogue
        # Specifically, check the LAST turn (Agent or Customer) for mentions of ANY known product.
        recent_mentions = []
        last_turn_text = ""
        if self.turns:
            # Check last 2 turns (User + Agent)
            for t in self.turns[-2:]:
                if t.transcript: 
                    # [FIX] transcript가 dict일 수 있으므로 문자열 변환
                    last_turn_text += " " + safe_str(t.transcript)
        
        # Product Index Removed
        # if self.product_index and hasattr(self.product_index, "all_names"):
        #      for name in self.product_index.all_names:
        #          if name in last_turn_text:
        #              recent_mentions.append(name)

        
        kws = []
        for k in ["해지", "위약금", "약정", "결합", "가족결합", "재결합", "요금제", "변경", "할인", "혜택", "동의", "개인정보", "인터넷", "IPTV"]:
            if k in dialog:
                kws.append(k)
        
        # Prioritize recent product mentions in the query
        parts = recent_mentions + kws[:10]
        
        # Add plans, dialogue, and segment hint, and DERIVED SIGNALS (VIP, Churn Risk etc)
        segment = self.customer.segment_guess or ""
        sig_text = " ".join(self.customer.signals)
        parts += [p for p in [self.customer.mobile_plan, self.customer.internet_plan, segment, sig_text, dialog] if p]
        
        return " | ".join(parts)[:1400]

    # [REMOVED] Legacy build_system_prompt (Logic moved to nodes.py)
    # def build_system_prompt(self, router_hint: Dict[str, Any]) -> str:
    #     pass

    async def step(self, session_id: str = "legacy_session") -> Dict[str, Any]:
        """
        [Refactored] Now wraps the LangGraph execution to ensure single source of truth.
        """
        from langchain_core.messages import HumanMessage
        
        # We need to construct input from the last turn
        if not self.turns:
            return {"next_step": "skip", "marketing_needed": False}
            
        last_turn = self.turns[-1]
        if last_turn.speaker != "customer":
            return {"next_step": "skip", "marketing_needed": False}
        
        # Use Persistent Graph
        graph = self.graph
        
        current_msg = HumanMessage(content=last_turn.transcript)
        
        # Prepare State
        # Note: We must inject 'self' as session_context
        initial_state = {
            "messages": [current_msg],
            # "session_context" is not state schema field, but some nodes might rely on state injection if not in config
            # Actually nodes.py uses config["configurable"]["session"]. 
        }
        
        config = {
            "configurable": {
                "thread_id": session_id,
                "session": self
            }
        }
        
        try:
            print(f"[Session] invoking Graph (persistent)... thread_id={session_id}")
            final_state = await graph.ainvoke(initial_state, config=config)
            
            # Map back to legacy result format for consumer compatibility
            return {
                "marketing_needed": final_state.get("marketing_needed", False),
                "marketing_type": final_state.get("marketing_type", "none"),
                "call_stage": final_state.get("conversation_stage", "listening"),
                "decision": {
                    "next_actions": final_state.get("next_actions", []) if final_state.get("next_actions") else [{"agent_script": {"opening": final_state.get("agent_script", "")}}]
                },
                "product_recommendations": final_state.get("product_candidates", []), # Schema match?
                # ... Map other fields if needed ...
            }
        except Exception as e:
            print(f"[Session] Graph step failed: {e}")
            import traceback
            traceback.print_exc()
            return {"marketing_needed": False, "error": str(e)}

    def _extract_script(self, result: Dict[str, Any]) -> str:
        # Helper to find the script in the deep result structure
        try:
            dec = result.get("decision", {})
            if isinstance(dec, dict):
                acts = dec.get("next_actions", [])
                if acts and isinstance(acts, list):
                    return acts[0].get("agent_script", {}).get("proposal") or acts[0].get("agent_script", {}).get("opening") or ""
        except:
            pass
        return ""


# -------------------------
# Builders
# -------------------------

def build_qdrant_client_from_env() -> QdrantClient:
    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_API_KEY")
    if not url or not key:
        raise RuntimeError("QDRANT_URL/QDRANT_API_KEY env not set")
    return QdrantClient(url=url, api_key=key, https=True, verify=False)

def build_session(customer_id: Optional[str] = None, phone: Optional[str] = None, customer_info: Optional[Dict[str, Any]] = None) -> MarketingSession:
    # 1. Mock Customer Data
    if customer_info:
        customer = CustomerProfile.from_dict(customer_info)
    else:
        # Fallback to default mock if no info provided
        customer = CustomerProfile.from_dict({
            "customer_id": customer_id or "UNKNOWN", 
            "phone": phone, 
            "rate_plan": "Unknown Plan",
            "monthly_fee_won": 50000
        })

    # 2. Vector DB (Qdrant)
    client = build_qdrant_client_from_env()

    # verify collection exists (read-only)
    cols = [c.name for c in client.get_collections().collections]
    if "cs_guideline" not in cols:
        raise RuntimeError(f"Qdrant collection missing: cs_guideline (found={cols})")

    qengine = QdrantSearchEngine(client=client, collection="cs_guideline", vector_name="dense", sparse_vector_name="sparse", category_key="metadata.category")

    # 3. LLM optional
    # LLM initialization (Debug Mode: Don't swallow errors)
    try:
        llm = OpenAICompatibleLLM()
    except Exception as e:
        print(f"[Session] ⚠️ LLM Init Failed: {e}")
        print("[Session] Falling back to MockLLM (No response generation)")
        llm = MockLLM()

    return MarketingSession(customer=customer, qdrant=qengine, llm=llm)
