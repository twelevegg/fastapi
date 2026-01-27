
import sys
import os
import asyncio
from typing import Dict, Any, Optional

from app.agent.marketing.session import build_session, MarketingSession

# Global session storage for the service
# Map: session_id -> MarketingSession
_sessions: Dict[str, MarketingSession] = {}

async def handle_marketing_message(turn: dict, session_id: str, customer_info: dict = None):
    """
    AgentManager compliant handler for Marketing AI.
    """
    global _sessions
    
    speaker = turn.get("speaker")
    transcript = turn.get("transcript", "")
    turn_id = turn.get("turn_id")
    
    # 1. Get or Create Session
    if session_id not in _sessions:
        print(f"[MarketingService] Creating new session: {session_id}")
        # Use customer info if provided, otherwise default
        customer_id = None
        phone = None
        if customer_info:
             # Basic mapping if available
             pass
        
        try:
             _sessions[session_id] = build_session(customer_id=customer_id, phone=phone)
        except Exception as e:
            print(f"[MarketingService] Session creation failed: {e}")
            return {"next_step": "skip", "reasoning": "Session init failed"}
            
    session = _sessions[session_id]
    
    # 2. Process Turn
    # If it's an agent (counselor/other AI) turn, just add to history
    if speaker == "agent" or speaker == "counselor":
        session.add_turn(speaker="agent", transcript=transcript, turn_id=turn_id)
        return {
            "next_step": "skip", 
            "reasoning": "Agent turn recorded",
            "agent_type": "marketing"
        }
        
    # If customer turn, add and step
    if speaker == "customer":
        session.add_turn(speaker="customer", transcript=transcript, turn_id=turn_id)
        
        # Run AI Step (RAG + LLM)
        try:
            result = await session.step()
        except Exception as e:
            print(f"[MarketingService] Step failed: {e}")
            return {"next_step": "skip", "reasoning": f"Error: {e}"}
            
        # 3. Extract Response
        # We need to map MarketingSession result to AgentManager/Guidance format if possible,
        # or just return the raw result and let the client handle it.
        # The Orchestrator expects: recommended_answer, work_guide, next_step
        
        marketing_needed = result.get("marketing_needed", False)
        marketing_type = result.get("marketing_type", "none")
        
        # Extract script
        agent_script = ""
        decision = result.get("decision", {})
        if isinstance(decision, dict):
             acts = decision.get("next_actions", [])
             if acts and isinstance(acts, list):
                 script_obj = acts[0].get("agent_script", {})
                 agent_script = script_obj.get("proposal") or script_obj.get("opening") or ""
        
        # If no marketing needed, we might want to skip or just be silent support
        # But for now, let's always return the script if it exists
        
        if not agent_script:
            agent_script = result.get("policy_answer", {}).get("answer", "")
            
        return {
            "agent_type": "marketing",
            "next_step": "generate" if agent_script else "skip",
            "recommended_answer": agent_script,
            "work_guide": f"Marketing Type: {marketing_type} (Needed: {marketing_needed})",
            "full_result": result # Optional: pass full result for debugging
        }
        
    return {"next_step": "skip", "reasoning": "Unknown speaker"}
