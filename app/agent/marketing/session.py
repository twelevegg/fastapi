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
import pandas as pd
import httpx

from qdrant_client import QdrantClient, models
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings


# -------------------------
# Paths / files
# -------------------------

CUSTOMER_XLSX = "고객_더미데이터_50_컬럼수정_v2.xlsx"
PRODUCT_XLSX  = "상품_데이터.xlsx"
QDRANT_ZIP    = "qdrant-setup-main.zip"

def find_in_drive(filename: str) -> Optional[str]:
    """
    Colab/Local 공용 파일 탐색 함수.

    우선순위:
    1) DATA_DIR 환경변수 (예: <ProjectRoot>/data)
    2) 프로젝트 루트 기준 ./data
    3) 현재 작업 디렉토리 기준 ./data
    4) (하위호환) Colab Drive 경로 /content/drive/MyDrive
    """
    roots: List[str] = []

    # 1) env override
    data_dir = (os.environ.get("DATA_DIR") or "").strip()
    if data_dir:
        roots.append(data_dir)

    # 2) project root: src/.. = project root
    here = os.path.dirname(os.path.abspath(__file__))          # .../app/agent/marketing
    proj_root = os.path.abspath(os.path.join(here, "../../../.."))      # .../<ProjectRoot>
    roots += [
        os.path.join(proj_root, "data"),
        proj_root,
    ]

    # 3) cwd
    roots += [
        os.path.join(os.getcwd(), "data"),
        os.getcwd(),
    ]

    # 4) backward compatibility: Colab Drive
    roots += [
        "/content/drive/MyDrive",
        "/content/drive/MyDrive/",
    ]

    for base in roots:
        if not base:
            continue
        p = os.path.join(base, filename)
        if os.path.isfile(p):
            return p
        hits = glob.glob(os.path.join(base, "**", filename), recursive=True)
        for h in hits:
            if os.path.isfile(h):
                return h
    return None


# -------------------------
# Safety: PII masking
# -------------------------

def mask_pii(text: str) -> str:
    if not text:
        return text
    t = text
    t = re.sub(r"\b01[0-9][- ]?\d{3,4}[- ]?\d{4}\b", "<PHONE>", t)
    t = re.sub(r"\b\d{6,}\b", "<NUM>", t)
    t = re.sub(r"([가-힣]{1,10}(?:로|길)\s*\d+(?:[가-힣0-9\s\-]*)?)", "<ADDRESS>", t)
    t = re.sub(r"\b\d+\s*호\b", "<HO>", t)
    t = re.sub(r"(성함이)\s*([가-힣]{2,4})", r"\1 <NAME>", t)
    t = re.sub(r"(상담사)\s*([가-힣]{2,4})", r"\1 <NAME>", t)
    t = re.sub(r"([가-힣]{2,4})\s*고객님", r"<NAME> 고객님", t)
    return t

def safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
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


class CustomerDB:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    @staticmethod
    def from_excel(path: str) -> "CustomerDB":
        df = pd.read_excel(path)
        return CustomerDB(df)

    def lookup(self, customer_id: Optional[str] = None, phone: Optional[str] = None) -> CustomerProfile:
        df = self.df
        row = None
        if customer_id and "고객 ID" in df.columns:
            hit = df[df["고객 ID"].astype(str) == str(customer_id)]
            if len(hit) > 0:
                row = hit.iloc[0]

        if row is None and phone and "전화번호" in df.columns:
            p = re.sub(r"\D", "", str(phone))
            phone_norm = df["전화번호"].astype(str).apply(lambda x: re.sub(r"\D", "", x))
            hit = df[phone_norm == p]
            if len(hit) > 0:
                row = hit.iloc[0]

        if row is None:
            row = df.iloc[0]

        prof = CustomerProfile(
            customer_id=safe_str(row.get("고객 ID")),
            phone=safe_str(row.get("전화번호")),
            subscription_type=safe_str(row.get("가입유형 (개인/법인 , 일반/알뜰폰/결합상품)")),
            mobile_plan=safe_str(row.get("통화 / 데이터 요금제명")),
            iptv_plan=safe_str(row.get("IPTV 상품 명")),
            internet_plan=safe_str(row.get("인터넷 상품 명")),
            monthly_fee_won=int(row.get("월 기본료")) if pd.notna(row.get("월 기본료")) else None,
            contract_active=True if safe_str(row.get("약정 여부(Y/N)")).upper() == "Y" else False if safe_str(row.get("약정 여부(Y/N)")) else None,
            contract_months=int(row.get("약정기간")) if pd.notna(row.get("약정기간")) else None,
            contract_remaining_months=int(row.get("잔여개월")) if pd.notna(row.get("잔여개월")) else None,
            discount_status=safe_str(row.get("할인 적용 여부(선택약정 / 가족결합 / 인터넷결합)")),
            addons=safe_str(row.get("부가서비스 목록(데이터 옵션, 컬러링, 보험)")),
            overage_1m=safe_str(row.get("초과 요금 발생 여부(1개월 전)")),
            overage_2m=safe_str(row.get("초과 요금 발생 여부(2개월 전)")),
            data_share=safe_str(row.get("데이터 이월 / 쉐어링 사용 여부")),
            roaming_history=safe_str(row.get("해외 로밍 이력")),
            region=safe_str(row.get("시/도 단위 거주 지역")),
            household=safe_str(row.get("1인가구/가족 가구")),
            remote_work=safe_str(row.get("재택 근무")),
            segment_guess=safe_str(row.get("학생/직장인 추정")),
        )
        prof.signals = self._derive_signals(prof)
        return prof

    @staticmethod
    def _derive_signals(p: CustomerProfile) -> List[str]:
        s = []
        if p.contract_remaining_months is not None and p.contract_remaining_months <= 1:
            s.append("약정 만료 임박(재약정/요금 최적화/이탈 방어 기회)")
        if (p.overage_1m or "").upper() == "Y" or (p.overage_2m or "").upper() == "Y":
            s.append("최근 초과요금 발생(상향/옵션/무제한 제안 기회)")
        if p.roaming_history and "없음" not in p.roaming_history:
            s.append("로밍 이력 존재(로밍 옵션/국제로밍 안내)")
        if p.discount_status and "미적용" in p.discount_status:
            s.append("할인 미적용(선택약정/가족결합/인터넷결합 점검)")
        if p.internet_plan:
            s.append("인터넷 결합 보유/가능(결합 할인/재결합/상향 여지)")
        if p.household and "가족" in p.household:
            s.append("가족 가구(가족결합/공유데이터/추가회선 여지)")
        if p.segment_guess and "학생" in p.segment_guess:
            s.append("학생 추정(유스/청년 혜택 적합 가능)")
        return s


# -------------------------
# Product DB search (semantic + keyword)
# -------------------------

@dataclass
class ProductItem:
    product_id: str
    kind: str
    name: str
    description: str
    price_text: str
    price_won: Optional[int]
    conditions: str
    cautions: str
    data: str
    share_data: str
    voice: str
    sms: str
    device: str
    benefits_discount: str
    benefits_basic: str
    benefits_special: str
    soldier_benefit: str
    extra_benefit: str
    url: str

    def to_compact(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "kind": self.kind,
            "name": self.name,
            "price_text": self.price_text,
            "price_won": self.price_won,
            "data": self.data,
            "share_data": self.share_data,
            "voice": self.voice,
            "sms": self.sms,
            "benefits_basic": (self.benefits_basic or "")[:220],
            "benefits_discount": (self.benefits_discount or "")[:220],
            "benefits_special": (self.benefits_special or "")[:220],
            "conditions": (self.conditions or "")[:180],
            "cautions": (self.cautions or "")[:180],
            "url": self.url,
        }

    def to_search_text(self) -> str:
        return (
            f"{self.kind} | {self.name} | {self.description} | 가격: {self.price_text} | "
            f"데이터: {self.data} | 공유: {self.share_data} | 음성: {self.voice} | 문자: {self.sms} | 스마트기기: {self.device} | "
            f"기본혜택: {self.benefits_basic} | 추가할인: {self.benefits_discount} | 특별혜택: {self.benefits_special} | "
            f"현역병사혜택: {self.soldier_benefit} | 기타혜택: {self.extra_benefit} | "
            f"가입조건: {self.conditions} | 유의사항: {self.cautions}"
        )


class ProductSearchIndex:
    def __init__(self, items: List[ProductItem]):
        self.items = items
        self._emb = None
        self._mat = None
        self._use_semantic = False

    @staticmethod
    def from_excel(path: str) -> "ProductSearchIndex":
        df = pd.read_excel(path)
        items = []
        for i, row in df.iterrows():
            price_text = safe_str(row.get("가격"))
            items.append(
                ProductItem(
                    product_id=f"PROD-{i:04d}",
                    kind=safe_str(row.get("종류")),
                    name=safe_str(row.get("상품명")),
                    description=safe_str(row.get("상품 설명")),
                    price_text=price_text,
                    price_won=parse_first_won(price_text),
                    conditions=safe_str(row.get("가입 조건")),
                    cautions=safe_str(row.get("유의사항")),
                    data=safe_str(row.get("제공 데이터")),
                    share_data=safe_str(row.get("공유 데이터")),
                    voice=safe_str(row.get("음성통화")),
                    sms=safe_str(row.get("문자메시지")),
                    device=safe_str(row.get("스마트기기")),
                    benefits_discount=safe_str(row.get("추가 할인 혜택")),
                    benefits_basic=safe_str(row.get("기본 혜택")),
                    benefits_special=safe_str(row.get("특별 혜택")),
                    soldier_benefit=safe_str(row.get("현역 병사 혜택")),
                    extra_benefit=safe_str(row.get("기타 추가 혜택")),
                    url=safe_str(row.get("URL")),
                )
            )
        return ProductSearchIndex(items)

    def build_semantic(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> None:
        try:
            self._emb = FastEmbedEmbeddings(model_name=model_name, normalize=True)
            vecs = self._emb.embed_documents([it.to_search_text() for it in self.items])
            mat = np.array(vecs, dtype=np.float32)
            mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
            self._mat = mat
            self._use_semantic = True
        except Exception:
            self._use_semantic = False
            self._emb = None
            self._mat = None

    def search(
        self,
        query: str,
        top_k: int = 6,
        strategy_hint: str = "none",
        must_include_names: Optional[List[str]] = None,
        semantic_weight: float = 0.65,
        keyword_weight: float = 0.35,
    ) -> List[ProductItem]:
        q = (query or "").strip()
        if not q:
            return self.items[:top_k]

        qt = q.lower()
        toks = [t for t in re.split(r"\s+", qt) if t][:12]
        bonus = ["해지", "결합", "할인", "약정", "로밍", "무제한", "데이터", "가족", "인터넷", "IPTV"]

        # keyword score
        kw_scores = []
        for it in self.items:
            text = it.to_search_text().lower()
            hit = 0
            for tk in toks:
                if tk in text:
                    hit += 1
            for b in bonus:
                if b in qt and b in text:
                    hit += 1
            kw_scores.append(hit)
        kw = np.array(kw_scores, dtype=np.float32)
        if kw.max() > 0:
            kw = kw / kw.max()

        # semantic score
        sem = np.zeros(len(self.items), dtype=np.float32)
        if self._use_semantic and self._emb is not None and self._mat is not None:
            try:
                qv = np.array(self._emb.embed_query(q), dtype=np.float32)
                qv = qv / (np.linalg.norm(qv) + 1e-12)
                s = self._mat @ qv
                sem = ((s + 1.0) / 2.0).astype(np.float32)
            except Exception:
                sem = np.zeros(len(self.items), dtype=np.float32)

        score = semantic_weight * sem + keyword_weight * kw
        ranked = np.argsort(-score).tolist()

        # force include current plan if provided
        forced = []
        if must_include_names:
            for name in must_include_names:
                name = (name or "").strip()
                if not name:
                    continue
                for i, it in enumerate(self.items):
                    if name == it.name or (name in it.name) or (it.name in name):
                        forced.append(i)

        out, seen = [], set()
        for i in forced + ranked:
            if i in seen:
                continue
            seen.add(i)
            out.append(self.items[i])
            if len(out) >= top_k:
                break

        return out


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

    def semantic(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(self.vs_dense.similarity_search_with_score(query=query, k=k, filter=self._filter(category)))

    def keyword(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(self.vs_sparse.similarity_search_with_score(query=query, k=k, filter=self._filter(category)))

    def hybrid(self, query: str, k: int = 6, category: Optional[str] = None) -> List[RetrievedItem]:
        return self._to_items(self.vs_hybrid.similarity_search_with_score(query=query, k=k, filter=self._filter(category)))

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

    def fused_search(self, query: str, final_k: int = 10, k_each: int = 8, category: Optional[str] = None) -> List[RetrievedItem]:
        sem = self.semantic(query, k=k_each, category=category)
        kw = self.keyword(query, k=k_each, category=category)
        hy = self.hybrid(query, k=k_each, category=category)
        return self._rrf([sem, kw, hy], [1.0, 1.0, 1.2], final_k=final_k)

    def staged_category_search(
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
            return self.fused_search(query, final_k=final_k, k_each=max(per_category_k, 6), category=None)

        per = []
        ws = []
        for c in cats:
            per.append(self.fused_search(query, final_k=per_category_k, k_each=per_category_k, category=c))
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


# -------------------------
# Prompts (high-control JSON, route-specific add-ons)
# -------------------------

BASE_SYSTEM = """\
당신은 통신/구독형 서비스의 콜센터 상담원(Agent)을 지원하는 “CS + 마케팅(업셀/해지방어) 코파일럿”이다.
입력:
- CUSTOMER_PROFILE_DB: 고객 DB(정형)
- PRODUCT_CANDIDATES: 상품 DB 후보(정형)
- EVIDENCE_QDRANT: 원격 Qdrant에서 검색된 약관/가이드 근거
- DIALOGUE_LAST_TURNS: 최근 대화 로그(ASR 오류/화자 혼동 가능)

핵심 목표:
1) 감정 분석(감정/의도/이탈위험)
2) 마케팅 개입 필요/불필요 판정(필요하면 upsell/retention/hybrid)
3) 상담원이 바로 읽을 수 있는 "다음 상담원 멘트"와 진행 플로우 생성
4) 정책/약관 준수 및 환각 방지

절대 금지:
- EVIDENCE_QDRANT 밖의 약관/절차/위약금 수치/확정 조건을 만들지 마라.
- PRODUCT_CANDIDATES 밖의 상품명/상품ID/혜택을 만들지 마라.
- 고객 PII(실명/전화/주소)를 그대로 반복하지 마라.
- "무조건 됩니다/보장" 같은 확정적 표현 금지 → "조회/조건 확인 후 안내"로 표현.

출력은 오직 JSON 단일 객체. 마크다운/설명문/코드블록 금지.

JSON 스키마(키 이름/구조 변경 금지):
{
  "call_stage": "verification|consent|problem_solving|offer_discussion|closing|unknown",
  "marketing_needed": true,
  "marketing_type": "none|support_only|upsell|retention|hybrid",
  "customer_state": {
    "sentiment": {"label": "positive|neutral|negative", "score": 0.0},
    "emotion_tags": ["anger|anxiety|disappointment|confusion|relief|..."],
    "primary_intent": "cancel|complaint|bundle|plan_change|price_inquiry|info_request|unknown",
    "churn_risk": {"level": "low|medium|high", "score": 0.0},
    "key_pain_points": ["..."]
  },
  "decision": {
    "why_marketing_needed_or_not": "한 문장",
    "branch_reason": "왜 이 분기인지(간결)",
    "next_questions": ["..."],
    "next_actions": [
      {
        "priority": 1,
        "type": "support|retention|upsell",
        "goal": "행동 목표",
        "rationale": "근거/이유(간결)",
        "agent_script": {
          "opening": "상담원이 바로 읽을 1~2문장",
          "empathy": "공감/안심 1문장(필요시)",
          "probing_questions": ["최대 3개"],
          "proposal": "제안/안내(근거 있을 때만 구체)",
          "objection_handling": ["최대 3개"],
          "closing": "마무리 1문장"
        },
        "evidence_doc_ids": ["DOC1"],
        "product_ids": ["PROD-0001"]
      }
    ],
    "micro_branches": [
      {
        "if_customer_says": "짧은 조건",
        "agent_response": "짧은 응답(한두 문장)",
        "goal": "support|retention|upsell",
        "evidence_doc_ids": ["DOC2"],
        "product_ids": ["PROD-0002"]
      }
    ]
  },
  "policy_answer": {
    "answer": "약관/절차/고지 기반 답변(근거 기반)",
    "evidence_doc_ids": ["DOC2"]
  },
  "product_recommendations": [
    {
      "product_id": "PROD-0001",
      "name": "상품명",
      "fit_reason": "왜 적합한가",
      "pitch": "상담원이 말할 짧은 제안 멘트",
      "must_check": ["가입조건/약정/대상 확인 등"],
      "notes": "유의사항 요약(있으면)"
    }
  ],
  "needs_more_info": false,
  "missing_info": ["..."],
  "safety_and_compliance": {
    "do_not_claim": ["..."],
    "checks_before_offer": ["..."],
    "risk_flags": ["..."]
  }
}
"""

ADDON_VERIFICATION_CONSENT = """\
[현재 초점: verification/consent]
- 본인확인/동의/고지 단계에서는 마케팅 제안(업셀)을 최소화한다.
- 고객이 먼저 결합/요금제 변경/혜택을 요구한 경우에만, "가능 여부 조회 후 안내" 수준으로 제한적 안내를 한다.
- 동의/고지 멘트는 짧고 정확하게.
"""

ADDON_RETENTION = """\
[현재 초점: retention(해지방어)]
- "전문 상담원" 페르소나를 유지하라. 고객의 감정에 '공감'하되, 감정에 휩쓸리지 말고 '해결책'으로 리드하라.
- 먼저 불편함에 대해 진정성 있게 사과/공감한다(1문장).
- 그 후, "하지만 고객님, 지금 해지하시는 것보다 [상품명]으로 변경하시는 것이 데이터는 2배 더 많고 요금은 [절약액]원 더 저렴합니다"와 같이 구체적인 수치와 혜택으로 설득한다.
- 제안은 2개 이하. 반드시 PRODUCT_CANDIDATES 중에서만 선택.
"""

ADDON_UPSELL = """\
[현재 초점: upsell(업셀링)]
- "베테랑 통신 컨설턴트"처럼 행동하라. 고객이 모르는 혜택을 찾아주는 전문가다.
- 요금 불만에는 "저도 요금이 많이 나오면 속상합니다"라고 공감한 뒤, "그래서 제가 고객님의 사용 패턴을 분석해봤는데요, [상품명]을 쓰시면 같은 가격에 데이터는 무제한입니다"라는 식으로 '전문적인 분석' 결과를 제시하라.
- 강매하는 느낌이 아니라, "고객님을 위해 찾아낸 최적의 솔루션"이라는 뉘앙스로 제안하라.
- 제안은 2개 이하. 반드시 PRODUCT_CANDIDATES 중에서만 선택.
"""

ADDON_HYBRID = """\
[현재 초점: hybrid]
- 1) 문제/불만 해결(또는 완화) 방향을 먼저 제시하고
- 2) 해결 이후 고객 부담을 줄이거나 만족도를 높이는 옵션(요금제/결합/혜택)을 제안한다.
- 제안은 1개가 원칙(최대 2개).
"""

ADDON_SUPPORT_ONLY = """\
[현재 초점: support_only]
- 마케팅 제안 없이 문의/절차/동의/약관 안내 중심으로 진행한다.
- missing_info/next_questions를 구체적으로 제시한다.
"""

USER_TEMPLATE = """\
[ROUTER_HINT]
{router_hint_json}

[STATE_PREV]
{state_prev_json}

[CUSTOMER_PROFILE_DB]
{customer_profile_json}

[DERIVED_SIGNALS]
{signals_json}

[PRODUCT_CANDIDATES]
{product_candidates_json}

[DIALOGUE_LAST_TURNS]
{dialogue_text}

[EVIDENCE_QDRANT]
{evidence_qdrant}

요청:
- ROUTER_HINT는 참고용이다. 실제 대화/근거에 따라 필요하면 수정해도 된다.
- 반드시 JSON 스키마를 지켜라(키/구조 변경 금지).
- 근거 없는 수치/혜택/위약금 확정 안내 금지.
"""


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
    def __init__(self, customer: CustomerProfile, product_index: ProductSearchIndex, qdrant: QdrantSearchEngine, llm: Any):
        self.customer = customer
        self.product_index = product_index
        self.qdrant = qdrant
        self.llm = llm
        
        # [NEW] Gatekeeper & Cache
        self.gatekeeper = Gatekeeper()
        self.cache = SemanticCache()
        
        # [NEW] Prefetch Cache
        # Stores Qdrant results for triggers found in fragments
        self._prefetch_cache: Dict[str, Any] = None
        
        self.turns: List[Turn] = []
        self.state_prev = {"call_stage": "unknown", "marketing_needed": False, "marketing_type": "none"}
        self.call_stage = "unknown"

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
        kws = []
        for k in ["해지", "위약금", "약정", "결합", "가족결합", "재결합", "요금제", "변경", "할인", "혜택", "동의", "개인정보", "인터넷", "IPTV"]:
            if k in dialog:
                kws.append(k)
        kws = kws[:10]
        parts = [p for p in [self.customer.mobile_plan, self.customer.internet_plan, " ".join(kws), dialog] if p]
        return " | ".join(parts)[:1400]

    def _system_prompt(self, router_hint: Dict[str, Any]) -> str:
        stage = router_hint.get("call_stage_hint", "unknown")
        mtype = router_hint.get("marketing_type_hint", "none")
        addon = ADDON_SUPPORT_ONLY
        if stage in ["verification", "consent"]:
            addon = ADDON_VERIFICATION_CONSENT
        elif mtype == "retention":
            addon = ADDON_RETENTION
        elif mtype == "upsell":
            addon = ADDON_UPSELL
        elif mtype == "hybrid":
            addon = ADDON_HYBRID
        elif mtype in ["support_only", "none"]:
            addon = ADDON_SUPPORT_ONLY
        return BASE_SYSTEM + "\n\n" + addon

    async def step(self) -> Dict[str, Any]:
        start_time = time.time()
        dialog = self.dialogue_text()
        
        # [Route 1] Safety Check (Gatekeeper)
        # Check the *latest* customer turn(s) for safety
        last_turn = self.turns[-1].transcript if self.turns and self.turns[-1].speaker == "customer" else ""
        safety = await self.gatekeeper.check_safety(last_turn)
        
        if not safety.is_safe:
            return {
                "call_stage": self.call_stage,
                "marketing_needed": False,
                "marketing_type": "none",
                "customer_state": {},
                "decision": {"next_actions": []},
                "product_recommendations": [],
                "_debug": {
                    "gatekeeper_result": f"Blocked: {safety.reason}"
                }
            }

        # [Route 2] Semantic Cache Check
        # [Route 2] Semantic Cache Check
        # cached_result = await self.cache.get(last_turn)
        # if cached_result:
        #     elapsed = (time.time() - start_time) * 1000
        #     cached_result["_meta"] = {"latency_ms": elapsed, "source": "cache"}
        #     return cached_result
        cached_result = None # Force Miss for Testing

        # [Route 3] Tier 2 Router (Fast LLM)
        # 1. Router (Tier 2) checks (Fast LLM)
        route_start = time.time()
        # [Route 3] Tier 2 Router (Fast LLM)
        # 1. Router (Tier 2) checks (Fast LLM)
        route_start = time.time()
        
        # [Context] Get last agent turn
        last_agent_turn = ""
        if len(self.turns) >= 2 and self.turns[-2].speaker == "agent":
            last_agent_turn = self.turns[-2].transcript
            
        route_result = await self.gatekeeper.semantic_route(last_turn, context=last_agent_turn) # Cached or LLM
        print(f"[Session] Router decision: {route_result} (took {time.time()-route_start:.2f}s)")      
        # Mapping to legacy hints for compatibility
        router_hint = {
            "call_stage_hint": "unknown", 
            "marketing_needed_hint": route_result.get("marketing_opportunity", False),
            "marketing_type_hint": "upsell" if route_result.get("marketing_opportunity") else "none",
            "reasons": [f"Intent: {route_result.get('intent')}, Sentiment: {route_result.get('sentiment')}"]
        }
        
        if not route_result.get("marketing_opportunity", False):
             # Skip expensive LLM if Tier 2 says no opportunity
             elapsed = (time.time() - start_time) * 1000
             return {
                "call_stage": self.call_stage,
                "marketing_needed": False,
                "marketing_type": "none",
                "customer_state": {},
                 "decision": {
                     "why_marketing_needed_or_not": "Fast Router: No opportunity detected",
                     "next_actions": []
                 },
                "product_recommendations": [],
                "_meta": {"latency_ms": elapsed, "source": "tier2_router"}
            }

        query = self.build_query()

        # Retrieval: staged with category weights; always include some terms for compliance
        stage = router_hint.get("call_stage_hint", "unknown")
        mtype = router_hint.get("marketing_type_hint", "none")

        # [Optimization] Check Prefetch Cache
        # If we have a fresh prefetch result (e.g. < 5 seconds old) that matches context, use it.
        # For simplicity, we just check if it exists and use it as 'evidence' augmentation
        
        q_items_pre = []
        if self._prefetch_cache:
            age = time.time() - self._prefetch_cache["timestamp"]
            if age < 5.0:
                print(f"[Session] Using Prefetched data (age={age:.2f}s)")
                q_items_pre = self._prefetch_cache["items"]
            self._prefetch_cache = None # Consume it

        if stage in ["verification", "consent"]:
            cats = ["terms", "guideline", "principle", "marketing"]
            weights = {"terms": 1.35, "guideline": 1.15, "principle": 1.05, "marketing": 0.9}
            always = {"terms": 3}
        elif mtype == "retention":
            cats = ["marketing", "guideline", "terms", "principle"]
            weights = {"marketing": 1.55, "guideline": 1.2, "terms": 1.05, "principle": 1.0}
            always = {"terms": 2}
        elif mtype == "upsell":
            cats = ["marketing", "guideline", "principle", "terms"]
            weights = {"marketing": 1.45, "guideline": 1.15, "principle": 1.05, "terms": 1.0}
            always = {"terms": 1}
        elif mtype == "hybrid":
            cats = ["guideline", "marketing", "terms", "principle"]
            weights = {"guideline": 1.25, "marketing": 1.25, "terms": 1.05, "principle": 1.0}
            always = {"terms": 2}
        else:
            cats = ["guideline", "terms", "principle", "marketing"]
            weights = {"guideline": 1.2, "terms": 1.1, "principle": 1.0, "marketing": 0.95}
            always = {"terms": 2}

            always = {"terms": 2}
        
        # Merge Pre-fetched items with current search if needed
        # Or if pre-fetched covers the need, skip search? (Advanced)
        # For now, we search normally but could mix in pre-fetched.
        q_items = self.qdrant.staged_category_search(query=query, final_k=10, per_category_k=6, categories=cats, cat_weights=weights, always_include=always)
        
        # Add pre-fetched to the pool if unique
        if q_items_pre:
             # simple dedup by doc_id
             existing_ids = {i.doc_id for i in q_items}
             for item in q_items_pre:
                 if item.doc_id not in existing_ids:
                     q_items.append(item)
                     
        q_context, q_ev = build_context(q_items)

        # Product candidates
        must = [self.customer.mobile_plan] if self.customer.mobile_plan else []
        strat = mtype if mtype in ["upsell", "retention", "hybrid"] else "none"
        p_items = self.product_index.search(query=query, top_k=6, strategy_hint=strat, must_include_names=must)
        p_json = [p.to_compact() for p in p_items]

        system_prompt = self._system_prompt(router_hint)
        user_prompt = USER_TEMPLATE.format(
            router_hint_json=json.dumps(router_hint, ensure_ascii=False, indent=2),
            state_prev_json=json.dumps(self.state_prev, ensure_ascii=False, indent=2),
            customer_profile_json=json.dumps(self.customer.to_prompt_json(), ensure_ascii=False, indent=2),
            signals_json=json.dumps(self.customer.signals, ensure_ascii=False, indent=2),
            product_candidates_json=json.dumps(p_json, ensure_ascii=False, indent=2),
            dialogue_text=dialog if dialog else "(대화 없음)",
            evidence_qdrant=q_context if q_context else "(검색 결과 없음)",
        )
        # Use dynamic model name in logs
        model_name = getattr(self.llm, "model", "Main LLM")
        print(f"[Session] 🧠 Calling {model_name} (Confirmed)...")
        llm_start = time.time()
        result = await self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2, max_tokens=1400)
        print(f"[Session] ✅ Main LLM finished in {time.time()-llm_start:.2f}s")

        # post-validate doc_ids/product_ids
        allowed_doc = {e["doc_id"] for e in q_ev}
        allowed_prod = {p["product_id"] for p in p_json}

        def clean_ids(lst, allowed):
            if not isinstance(lst, list):
                return []
            return [x for x in lst if x in allowed]

        dec = result.get("decision", {})
        if isinstance(dec, dict):
            acts = dec.get("next_actions", [])
            if isinstance(acts, list):
                for a in acts:
                    if isinstance(a, dict):
                        a["evidence_doc_ids"] = clean_ids(a.get("evidence_doc_ids", []), allowed_doc)
                        a["product_ids"] = clean_ids(a.get("product_ids", []), allowed_prod)
            mbs = dec.get("micro_branches", [])
            if isinstance(mbs, list):
                for b in mbs:
                    if isinstance(b, dict):
                        b["evidence_doc_ids"] = clean_ids(b.get("evidence_doc_ids", []), allowed_doc)
                        b["product_ids"] = clean_ids(b.get("product_ids", []), allowed_prod)

        pol = result.get("policy_answer", {})
        if isinstance(pol, dict):
            pol["evidence_doc_ids"] = clean_ids(pol.get("evidence_doc_ids", []), allowed_doc)

        pr = result.get("product_recommendations", [])
        if isinstance(pr, list):
            result["product_recommendations"] = [r for r in pr if isinstance(r, dict) and safe_str(r.get("product_id")) in allowed_prod]

        # update state
        self.state_prev["call_stage"] = safe_str(result.get("call_stage")) or self.state_prev["call_stage"]
        self.state_prev["marketing_needed"] = bool(result.get("marketing_needed", False))
        self.state_prev["marketing_type"] = safe_str(result.get("marketing_type")) or self.state_prev["marketing_type"]

        result["_debug"] = {
            "router_hint": router_hint,
            "retrieval_query_masked": mask_pii(query),
            "qdrant_evidence": q_ev,
            "product_candidates": p_json,
        }
        
        # [Cache Set]
        await self.cache.set(last_turn, result)
        
        # [Memory] Save Agent Turn
        agent_script = self._extract_script(result)
        if agent_script:
            self.add_turn(speaker="agent", transcript=agent_script)
        
        elapsed = (time.time() - start_time) * 1000
        result["_meta"] = {"latency_ms": elapsed, "source": "tier3_llm"}
        
        return result

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
    return QdrantClient(url=url, api_key=key)

def build_session(customer_id: Optional[str] = None, phone: Optional[str] = None) -> MarketingSession:
    cpath = find_in_drive(CUSTOMER_XLSX)
    ppath = find_in_drive(PRODUCT_XLSX)
    if not cpath:
        raise FileNotFoundError(f"Missing in Drive: {CUSTOMER_XLSX}")
    if not ppath:
        raise FileNotFoundError(f"Missing in Drive: {PRODUCT_XLSX}")

    cust_db = CustomerDB.from_excel(cpath)
    customer = cust_db.lookup(customer_id=customer_id, phone=phone)

    prod = ProductSearchIndex.from_excel(ppath)
    prod.build_semantic()

    client = build_qdrant_client_from_env()

    # verify collection exists (read-only)
    cols = [c.name for c in client.get_collections().collections]
    if "cs_guideline" not in cols:
        raise RuntimeError(f"Qdrant collection missing: cs_guideline (found={cols})")

    qengine = QdrantSearchEngine(client=client, collection="cs_guideline", vector_name="dense", sparse_vector_name="sparse", category_key="metadata.category")

    # LLM optional
    # LLM initialization (Debug Mode: Don't swallow errors)
    try:
        llm = OpenAICompatibleLLM()
    except Exception as e:
        print(f"[Session] ⚠️ LLM Init Failed: {e}")
        print("[Session] Falling back to MockLLM (No response generation)")
        llm = MockLLM()

    return MarketingSession(customer=customer, product_index=prod, qdrant=qengine, llm=llm)
