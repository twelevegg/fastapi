import json
import time
from langchain_core.messages import AIMessage, HumanMessage
from app.agent.marketing.state import MarketingState

# access to session.py resources via state["session_context"]

from langchain_core.runnables import RunnableConfig

async def analyze_node(state: MarketingState, config: RunnableConfig):
    """
    1. Router / Gatekeeper Logic
    2. Intent Classification
    """
    print("--- [Marketing] Node: Analyze ---")
    session = config["configurable"]["session"] # MarketingSession instance
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    
    # 1. Check Safety (Gatekeeper Only) - Re-verify just in case
    # 1. Check Safety (Gatekeeper Only) - Re-verify just in case
    should_skip = await session.gatekeeper.should_skip_marketing(last_msg)
    if should_skip: 
        print(f"--- [Marketing] Gatekeeper Blocked: Unsafe/Support-Only ---")
        return {
            "conversation_stage": state.get("conversation_stage", "listening"),
            "marketing_needed": False,
            "marketing_type": "none",
            "generated_reasoning": "Gatekeeper Block (Safety/Abuse/VIP)"
        } 

    # 2. [Deep Analysis] Veteran Mode
    # Instead of reusing the fast router, we conduct a deep-dive with the main LLM.
    from app.agent.marketing.prompts import DEEP_ANALYSIS_SYSTEM
    
    # Context
    # Context - Use full dialogue history for better analysis
    dialogue_history = session.dialogue_text(last_n=6)
    
    # Construct Prompt
    # Convert signals list to string
    signals_str = ", ".join(session.customer.signals) if session.customer.signals else "없음"
    
    user_prompt = f"""
    [대화 기록 (최근 상황)]
    {dialogue_history}
    
    [현재 고객 발언]
    "{last_msg}"
    
    [고객 프로필 (Deep Dive)]
    요금제: {session.customer.mobile_plan}
    약정상태: {session.customer.contract_remaining_months}개월 남음
    월납부액: {session.customer.monthly_fee_won}원
    특이사항(Signals): {signals_str}
    """
    
    # State Machine Logic
    current_stage = state.get("conversation_stage", "listening")
    next_stage = current_stage
    
    # Analyze Intent using DEEP_ANALYSIS Logic
    try:
        print(f"--- [Marketing] Deep Analysis (Stage: {current_stage}) ---")
        analysis = await session.llm.chat_json(
            system_prompt=DEEP_ANALYSIS_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.0
        )
        # Raw Analysis
        marketing_needed = analysis.get("marketing_opportunity", False)
        intent = analysis.get("intent", "neutral")
        churn_reason = analysis.get("churn_reason", "unknown")
        objection_reason = analysis.get("objection_reason", "unknown")
        reasoning = analysis.get("reasoning", "No reason provided")
        
        # -----------------------------------------------------
        # State Transition Table
        # -----------------------------------------------------
        marketing_type = "none"
        
        if current_stage == "listening":
            if marketing_needed:
                next_stage = "proposing"
                
                # [Global Price Check] If any signal of price sensitivity
                is_churn_intent = ("해지" in last_msg or "탈퇴" in last_msg or intent == "churn")
                is_price_sensitive = (churn_reason == "price" or objection_reason == "price" or "싸" in last_msg or "저렴" in last_msg)

                if is_churn_intent:
                    # Default: Assume Price Sensitivity unless explicit Quality complaint
                    if churn_reason == "quality": 
                        marketing_type = "retention" # Pivot to Upsell (Better Quality)
                    else: 
                        marketing_type = "retention_price" # Safe Downsell (Price/Service)
                elif is_price_sensitive:
                    marketing_type = "cost_optimization" # [NEW] Pure Cost Saving (No Churn Intent)
                else: 
                    # Complaint (Quality) or General Marketing Need -> Upsell
                    marketing_type = "upsell"
            else:
                next_stage = "listening"

        elif current_stage == "proposing":
            if intent in ["objection", "question"]:
                # [Pivot Logic] If objection is specifically about PRICE, treat it as a rejection of this item -> Switch to Downsell (Price Retention)
                if intent == "objection" and objection_reason == "price":
                    # Check if user wants ALTERNATIVE ("too expensive, show me cheaper") vs just complaining
                    next_stage = "proposing" # Re-propose new
                    marketing_type = "cost_optimization" # Switch to Cost Saving
                    marketing_needed = True
                else:
                    # Generic objection or question?
                    # Check for "Alternative" triggers manually if LLM classified as question
                    if any(x in last_msg for x in ["다른", "딴거", "그거 말고", "제외하고"]):
                         next_stage = "proposing"
                         marketing_type = "alternative"
                         marketing_needed = True
                    else:
                        next_stage = "negotiating" # Defend
                        marketing_type = "explanation"
                        marketing_needed = True
            elif intent == "alternative":
                next_stage = "proposing" # Re-propose new item
                marketing_type = "alternative"
                marketing_needed = True
            elif intent == "neutral" and not marketing_needed:
                # User ignored proposal? Stay proposing or back to listening?
                # Check for "Alternative" triggers manually even if intent is neutral
                if any(x in last_msg for x in ["다른", "딴거", "그거 말고", "제외하고"]):
                        next_stage = "proposing"
                        marketing_type = "alternative"
                        marketing_needed = True
                elif marketing_needed:
                    next_stage = "proposing"
                    marketing_type = "upsell"
                else:
                     next_stage = "listening"

        elif current_stage == "negotiating":
            if intent == "alternative":
                # Negotiation failed, user wants pivot
                next_stage = "proposing"
                marketing_type = "alternative"
                marketing_needed = True
            elif intent in ["objection", "question"]:
                # Continued negotiation
                next_stage = "negotiating"
                marketing_type = "explanation"
                marketing_needed = True
            elif intent == "marketing": 
                # User might be accepting or asking specifically for sign-up
                # Ideally, if positive -> Closing
                # For now, treat as explanation/hybrid
                 next_stage = "closing"
                 marketing_type = "hybrid" # or closing type
                 marketing_needed = True
        
        # Fallback / Override for Safety
        if not marketing_needed:
            marketing_type = "none"
            # If we were proposing/negotiating and opportunity vanished, maybe go to closing or listening?
            # Let's default to listening to be safe.
            # But if we are in negotiating, we shouldn't just drop it unless explicit 'no'.
            pass

        print(f"--- [Marketing] State Transition: {current_stage} -> {next_stage} (Type: {marketing_type}) ---")
        
    except Exception as e:
        print(f"--- [Marketing] Analysis Failed: {e}")
        marketing_needed = False
        marketing_type = "none"
        reasoning = "Analysis Error"
        next_stage = current_stage

    # Update State
    return {
        "call_stage": "unknown", # Legacy
        "conversation_stage": next_stage,
        "marketing_needed": marketing_needed,
        "marketing_type": marketing_type,
        "generated_reasoning": reasoning
    }

async def retrieve_node(state: MarketingState, config: RunnableConfig):
    """
    1. Build Query
    2. Search Qdrant (Terms/Guidelines)
    3. Search ProductDB
    """
    print("--- [Marketing] Node: Retrieve ---")
    session = config["configurable"]["session"]
    messages = state["messages"]
    
    # Reuse session.build_query() logic? 
    # session object has 'turns' list, but LangGraph maintains 'messages'.
    # We need to sync them or just rely on session.turns if we keep add_turn sync?
    # MarketingService calls session.add_turn BEFORE invoking graph. 
    # So session.turns is up to date! We can use session.build_query().
    
    query = session.build_query()
    
    # Configure weights based on type
    mtype = state.get("marketing_type", "none")
    stage = state.get("call_stage", "unknown")
    
    # [State Machine] Sticky Context vs Alternative
    
    # 1. Sticky Context (Explanation/Negotiation)
    # If we are in 'negotiating' stage (mtype=explanation), we MUST reuse the current proposal.
    if mtype == "explanation" and state.get("current_proposal"):
        print(f"--- [Marketing] Sticky Context Active: Reusing {len(state['current_proposal'])} products ---")
        return {
            "search_query": query,
            "retrieved_items": [], 
            "context_text": "(이전 제안 설명)", 
            "product_candidates": state["current_proposal"],
            # Keep state as is
        }
    
    # 2. Alternative Proposal (Pivot) or Price Downsell
    # If we are pivoting (alternative) or downsizing (retention_price), we must:
    #   a) Add current proposal to rejected list
    #   b) Clear current proposal
    #   c) Search excluding the rejected list
    exclude_names = list(state.get("rejected_proposals", []))
    current_prop = state.get("current_proposal", [])
    
    # Trigger Rejection Logic for both Alternative and Price Retention (Implicit Rejection)
    # Trigger Rejection Logic for both Alternative and Price Retention (Implicit Rejection)
    if mtype in ["alternative", "retention_price", "cost_optimization"]:
        if current_prop:
            names = [p["name"] for p in current_prop]
            exclude_names.extend(names)
            print(f"--- [Marketing] Rejection Logic ({mtype}): Excluding {names} ---")
            
    # Logic copied from session.py (simplified for readability)
    cats = ["marketing", "guideline", "terms"]
    weights = None
    always = None
    
    if mtype == "retention":
        weights = {"marketing": 1.55, "guideline": 1.2}
    elif mtype == "upsell":
        weights = {"marketing": 1.45, "guideline": 1.15}
    elif mtype in ["retention_price", "cost_optimization"]:
        # Boost budget/saving keywords?
        weights = {"marketing": 1.6, "guideline": 1.0}
        
    q_items = await session.qdrant.staged_category_search(
        query=query, 
        final_k=8, 
        categories=cats, 
        cat_weights=weights
    )
    
    # Separation: Split items into 'evidence' and 'products' based on category
    evidence_items = [it for it in q_items if it.category != "marketing"]
    product_items = [it for it in q_items if it.category == "marketing"]

    # Context Building
    from app.agent.marketing.session import build_context
    context_text, ev_list = build_context(evidence_items)

    
    # [Price Constraint]
    max_price = None
    # [Price Constraint]
    max_price = None
    if session.customer.monthly_fee_won:
        # Check context for price sensitivity even in Alternative
        # If user objected to Price, or previous intent was cost optimization
        is_price_alt = False
        if mtype == "alternative":
            # Check keywords or objection reason
             last_msg = messages[-1].content if messages else ""
             if "비싸" in last_msg or "가격" in last_msg or "요금" in last_msg or state.get("objection_reason") == "price":
                 is_price_alt = True

        if mtype == "cost_optimization" or (mtype == "alternative" and is_price_alt):
            # Strict: User wants CHEAPER. Max = Current Fee.
            max_price = session.customer.monthly_fee_won
            print(f"--- [Marketing] Price Constraint (Strict): Max {max_price} KRW (Cost/Alt-Price) ---")
        elif mtype == "retention_price":
             # Buffer: User complained about price, but afford a small buffer (10%) for high-value upsell chance
            max_price = int(session.customer.monthly_fee_won * 1.1)
            print(f"--- [Marketing] Price Constraint (Buffered): Max {max_price} KRW ---")
    
    # Product Search (Now using Qdrant 'marketing' items)
    # Map Qdrant items to Product Candidate JSON format
    p_json = []
    
    # [Price Constraint] - Filter product_items based on price (if metadata exists)
    # Assuming metadata has 'price' or we parse it from content? 
    # For now, let's just pass them all or do simple filtering if metadata is reliable.
    
    filtered_products = []
    for it in product_items:
        # Exclude rejected
        name = it.metadata.get("title", "")
        if any(ex in name for ex in exclude_names):
            continue
            
        # Price check (if available in metadata)
        # Assuming metadata["price_won"] exists or we skip check
        price = it.metadata.get("price_won")
        if max_price is not None and price and isinstance(price, (int, float)):
             if price > max_price:
                 continue
                 
        filtered_products.append(it)
        
    # Limit to top 4
    for it in filtered_products[:4]:
        p_json.append({
            "product_id": it.doc_id,
            "name": it.metadata.get("title", "Unknown"),
            "price_text": str(it.metadata.get("price_won", "가격 정보 없음")),
            "description": (it.page_content or "")[:200],
            "benefits": it.metadata.get("summary", ""),
            "url": it.metadata.get("url", "")
        })
    
    return {
        "search_query": query,
        "retrieved_items": ev_list,
        "context_text": context_text,
        "product_candidates": p_json,
        "rejected_proposals": exclude_names, # Update State
        # If alternative, we effectively cleared current_proposal by searching new ones. 
        # The new ones will be set in generate_node or here? 
        # State updates strictly merge. So 'product_candidates' will be new. 
        # 'current_proposal' should be updated in generate_node when we DECIDE to pitch these.
    }


async def generate_node(state: MarketingState, config: RunnableConfig):
    """
    1. Assemble Prompt
    2. Call Main LLM
    3. Parse Result
    """
    print("--- [Marketing] Node: Generate ---")
    session = config["configurable"]["session"]
    
    # Check skip
    if not state.get("marketing_needed", False):
         return {
             "agent_script": "", 
             "next_actions": []
         }
         
    # [Safety Net] No Product Data -> No Pitch (Unless it's just an explanation)
    p_json = state.get("product_candidates", [])
    if state.get("marketing_type") in ["upsell", "retention", "cost_optimization", "alternative"] and not p_json:
        print("[Marketing] 🛑 Safety Net: No product candidates found. Aborting pitch.")
        return {
            "agent_script": "고객님, 현재 고객님의 조건에 딱 맞는 추천 상품이 확인되지 않습니다. 혹시 다른 불편한 점이 있으신가요?",
            "marketing_type": "none",
            "next_actions": []
        }

    # Prepare Data for Prompt
    # Simplify: Just dump the essential JSONs
    from app.agent.marketing.prompts import BASE_SYSTEM, STRATEGY_UPSELL, STRATEGY_RETENTION, STRATEGY_RETENTION_PRICE, STRATEGY_COST_OPTIMIZATION, STRATEGY_DEFAULT, STRATEGY_EXPLANATION, STRATEGY_ALTERNATIVE
    
    # Determine Strategy based on marketing_type hints from Analyzer or specific keywords
    m_type_hint = state.get("marketing_type", "upsell")
    
    if m_type_hint == "upsell":
        strategy_text = STRATEGY_UPSELL
    elif m_type_hint == "retention":
        strategy_text = STRATEGY_RETENTION
    elif m_type_hint == "retention_price":
        strategy_text = STRATEGY_RETENTION_PRICE
    elif m_type_hint == "cost_optimization":
        strategy_text = STRATEGY_COST_OPTIMIZATION
    elif m_type_hint == "explanation":
        strategy_text = STRATEGY_EXPLANATION
    elif m_type_hint == "alternative":
        strategy_text = STRATEGY_ALTERNATIVE
    else:
        strategy_text = STRATEGY_DEFAULT
    
    # Construct System Prompt
    system_prompt = BASE_SYSTEM.format(
        customer_profile_json=json.dumps(session.customer.to_prompt_json(), ensure_ascii=False),
        product_candidates_json=json.dumps(state.get("product_candidates", []), ensure_ascii=False),
        dialogue_text=session.dialogue_text(last_n=12),
        evidence_qdrant=state.get("context_text") or "(근거 없음)"
    )
    
    # Context Injection
    user_prompt = f"""
    [현재 적용 전략]
    {strategy_text}
    
    [고객의 마케팅 니즈]
    {state.get('generated_reasoning', '분석 불가')}

    [지시사항]
    위 정보를 바탕으로 마케팅 전략을 수행하라.
    특히, 상품을 추천한다면 반드시 'marketing_proposal' 필드에 "Before vs After" 비교 정보를 채워라.
    
    위 정보를 바탕으로 최적의 'recommended_pitch'를 생성하라.
    """
    
    # Call LLM
    try:
        # Using raw openai client via session wrapper for flexibility, or simple structure
        result = await session.llm.chat_json(
            system_prompt=system_prompt, 
            user_prompt=user_prompt, 
            temperature=0.3, # Slightly higher for creativity in pitch
            max_tokens=600
        )
        
        agent_script = result.get("recommended_pitch", "")
        reasoning = result.get("reasoning", "")
        marketing_proposal = result.get("marketing_proposal") # Extract Proposal JSON
        
        if not agent_script:
             agent_script = {"ment": "- [시스템] 제안 내용 생성 중..."}

        # [Fallback] If LLM failed to generate proposal but we have products, generate it manually
        if not marketing_proposal and state.get("product_candidates"):
            best_product = state.get("product_candidates")[0]
            print(f"[Marketing] ⚠️ LLM returned null proposal. FLAGGING FALLBACK for {best_product['name']}")
            
            # Simple Rule-based Construction (Dashboard Style)
            current_plan = session.customer.mobile_plan or "현재 요금제"
            
            # Auto-generate succinct pitch for fallback (Structured JSON)
            agent_script = {
                "needs": "혜택/요금 최적화 필요",
                "recommendation": best_product['name'],
                "comparison": f"{current_plan} -> {best_product['name']}",
                "ment": "월 이용료는 비슷하지만 혜택은 2배 더 많습니다."
            }
            
            marketing_proposal = {
                "card_title": f"{best_product['name']} 제안",
                "comparison": {
                    "before": {"label": "현재", "desc": current_plan, "price_text": f"{session.customer.monthly_fee_won}원"},
                    "after": {
                        "label": "제안", 
                        "desc": best_product['name'], 
                        "price_text": best_product.get('price_text', '가격 문의'), 
                        "highlight": True
                    }
                },
                "arrow_text": "스펙 업그레이드",
                "benefits": [best_product.get('benefits', '상세 혜택')]
            }

        # [State Machine] Save Proposal for Sticky Context
        # If we just pitched something (upsell/retention), save it to STATE.
        new_proposal_state = state.get("current_proposal") # Default keep existing
        
        if result.get("marketing_type") in ["upsell", "retention", "cost_optimization"] and state.get("product_candidates"):
             new_proposal_state = state.get("product_candidates")
             
        # If alternative, we also pitch, so save it as current
        if result.get("marketing_type") == "alternative" and state.get("product_candidates"):
             new_proposal_state = state.get("product_candidates")

        return {
            "agent_script": agent_script,
            "marketing_type": result.get("marketing_type", m_type_hint),
            "generated_reasoning": reasoning,
            "marketing_proposal": marketing_proposal, # Persist to State
            "current_proposal": new_proposal_state 
        }
        
    except Exception as e:
        print(f"[Marketing] Generate Failed: {e}")
        return {
            "agent_script": "죄송합니다. 잠시 시스템 확인 후 안내드리겠습니다.",
            "marketing_type": "none"
        }
