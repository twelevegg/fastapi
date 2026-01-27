
import sys
import os
import asyncio
from typing import Dict, Any, Optional

from app.agent.marketing.session import build_session, MarketingSession
from app.agent.marketing.graph import build_marketing_graph
from langchain_core.messages import HumanMessage, AIMessage

# Initialize Graph Once (Global)
marketing_graph = build_marketing_graph()

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
        # Synchronize session history (Legacy support for session.turns)
        session.add_turn(speaker="customer", transcript=transcript, turn_id=turn_id)
        
        # Prepare Graph Inputs
        # We construct 'messages' list for LangGraph from session.turns or just pass the new message?
        # LangGraph MemorySaver will persist state, but our 'session_id' key in config handles thread.
        # However, we are using 'session_context' to pass the heavy object.
        
        # We need to construct the current turn message
        current_msg = HumanMessage(content=transcript)
        
        graph_config = {
            "configurable": {
                "thread_id": session_id,
                "session": session # Inject resource via config (non-serializable)
            }
        }
        initial_state = {
            "messages": [current_msg], # add_messages reducer will append this
            # "session_context": session, # REMOVED: Passed via config
            "session_id": session_id,
            "marketing_needed": False # Default
        }
        
        # Run Graph
        try:
            print(f"[MarketingService] Invoking Graph for {session_id}")
            final_state = await marketing_graph.ainvoke(initial_state, config=graph_config)
        except Exception as e:
            print(f"[MarketingService] Graph failed: {e}")
            import traceback
            traceback.print_exc()
            return {"next_step": "skip", "reasoning": f"Error: {e}"}
            
        # Extract Results from Final State
        marketing_needed = final_state.get("marketing_needed", False)
        marketing_type = final_state.get("marketing_type", "none")
        agent_script = final_state.get("agent_script", "")
        
        # Update Session History with Agent Response (for next turn context)
        if agent_script:
            session.add_turn(speaker="agent", transcript=agent_script)
            
        return {
            "agent_type": "marketing",
            "next_step": "generate" if agent_script else "skip",
            "recommended_answer": agent_script,
            "work_guide": f"Marketing Type: {marketing_type} (Needed: {marketing_needed})",
            # "full_result": final_state # Optional
        }
            

        
    return {"next_step": "skip", "reasoning": "Unknown speaker"}
