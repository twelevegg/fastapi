import json
import time
from langchain_core.messages import AIMessage, HumanMessage
from app.agent.marketing.state import MarketingState

# access to session.py resources via state["session_context"]

async def analyze_node(state: MarketingState):
    """
    1. Router / Gatekeeper Logic
    2. Intent Classification
    """
    print("--- [Marketing] Node: Analyze ---")
    session = state["session_context"] # MarketingSession instance
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    
    # 1. Check Safety
    is_safe = await session.gatekeeper.should_skip_marketing(last_msg)
    if is_safe: # naming is confusing. should_skip returns True if unsafe?
        # Let's check session.py logic: if not safety.is_safe -> return True (Skip)
        pass 
        
    # We'll re-use session.gatekeeper.semantic_route
    # But we need context (previous agent turn)
    last_agent_turn = ""
    if len(messages) >= 2 and isinstance(messages[-2], AIMessage):
        last_agent_turn = messages[-2].content

    route_result = await session.gatekeeper.semantic_route(last_msg, context=last_agent_turn)
    # route_result = {"intent":..., "marketing_opportunity": bool, ...}
    
    marketing_needed = route_result.get("marketing_opportunity", False)
    marketing_type = "upsell" if marketing_needed else "none" # Simplified mapping
    
    # Update State
    return {
        "call_stage": "unknown",
        "marketing_needed": marketing_needed,
        "marketing_type": marketing_type,
        "generated_reasoning": f"Intent: {route_result.get('intent')}, Sentiment: {route_result.get('sentiment')}"
    }

async def retrieve_node(state: MarketingState):
    """
    1. Build Query
    2. Search Qdrant (Terms/Guidelines)
    3. Search ProductDB
    """
    print("--- [Marketing] Node: Retrieve ---")
    session = state["session_context"]
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
    
    # Logic copied from session.py (simplified for readability)
    cats = ["marketing", "guideline", "terms"]
    weights = None
    always = None
    
    if mtype == "retention":
        weights = {"marketing": 1.55, "guideline": 1.2}
    elif mtype == "upsell":
        weights = {"marketing": 1.45, "guideline": 1.15}
        
    q_items = session.qdrant.staged_category_search(
        query=query, 
        final_k=6, 
        categories=cats, 
        cat_weights=weights
    )
    
    # Context Building
    from app.agent.marketing.session import build_context
    context_text, ev_list = build_context(q_items)
    # ev_list contains simple dicts
    
    # Product Search
    p_items = session.product_index.search(query=query, top_k=4)
    p_json = [p.to_compact() for p in p_items]
    
    return {
        "search_query": query,
        "retrieved_items": ev_list,   # For evidence
        "context_text": context_text, # For LLM prompt
        "product_candidates": p_json
    }

async def generate_node(state: MarketingState):
    """
    1. Assemble Prompt
    2. Call Main LLM
    3. Parse Result
    """
    print("--- [Marketing] Node: Generate ---")
    session = state["session_context"]
    
    # Check skip
    if not state.get("marketing_needed", False):
         return {
             "agent_script": "", 
             "next_actions": []
         }

    # Prepare Data for Prompt
    # We need to construct the prompt using session._system_prompt and USER_TEMPLATE
    # But session.state_prev needs to be updated or we use graph state?
    # Let's rely on session.state_prev for now (Side effect!) or pass state.
    
    # Actually, let's use the graph state to feed the prompt
    from app.agent.marketing.session import USER_TEMPLATE
    
    # We need to mock/reconstruct the hint/json objects
    router_hint = {
        "marketing_needed_hint": state.get("marketing_needed"),
        "marketing_type_hint": state.get("marketing_type"),
        "reasons": [state.get("generated_reasoning")]
    }
    
    customer_json = session.customer.to_prompt_json()
    signals_json = session.customer.signals
    p_json = state.get("product_candidates", [])
    
    # formatting
    system_prompt = session._system_prompt(router_hint)
    user_prompt = USER_TEMPLATE.format(
        router_hint_json=json.dumps(router_hint, ensure_ascii=False, indent=2),
        state_prev_json=json.dumps(session.state_prev, ensure_ascii=False, indent=2), # Legacy state
        customer_profile_json=json.dumps(customer_json, ensure_ascii=False, indent=2),
        signals_json=json.dumps(signals_json, ensure_ascii=False, indent=2),
        product_candidates_json=json.dumps(p_json, ensure_ascii=False, indent=2),
        dialogue_text=session.dialogue_text(last_n=6),
        evidence_qdrant=state.get("context_text") or "(검색 결과 없음)",
    )
    
    # Call LLM
    start_t = time.time()
    result = await session.llm.chat_json(
        system_prompt=system_prompt, 
        user_prompt=user_prompt, 
        temperature=0.2, 
        max_tokens=1000
    )
    
    # Parse Result
    # Extract script
    agent_script = ""
    decision = result.get("decision", {})
    if isinstance(decision, dict):
         acts = decision.get("next_actions", [])
         if acts and isinstance(acts, list):
             script_obj = acts[0].get("agent_script", {})
             agent_script = script_obj.get("proposal") or script_obj.get("opening") or ""
    
    if not agent_script:
        agent_script = result.get("policy_answer", {}).get("answer", "")

    return {
        "agent_script": agent_script,
        "next_actions": decision.get("next_actions", []),
        "marketing_type": result.get("marketing_type", state.get("marketing_type"))
    }
