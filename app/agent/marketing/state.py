from typing_extensions import TypedDict
from typing import Annotated, Optional, List, Literal, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class MarketingState(TypedDict):
    # Core Messages (Chat History)
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Metadata / Context
    session_id: str
    # session_context removed (passed via config to avoid serialization error)
    customer_id: Optional[str]
    customer_profile: Optional[Dict[str, Any]] # Raw or Processed profile
    
    # Analysis Results
    call_stage: Optional[str] # Legacy, keeping for compatibility or removing? Let's keep as hint but use conversation_stage
    conversation_stage: Literal["listening", "proposing", "negotiating", "closing"] # [NEW] Core State
    marketing_needed: bool
    marketing_type: Literal["none", "support_only", "upsell", "retention", "retention_price", "cost_optimization", "hybrid", "explanation", "alternative"]
    
    # Retrieval
    search_query: Optional[str]
    retrieved_items: List[Dict[str, Any]] # Raw items from Qdrant
    context_text: Optional[str] # Formatted string for LLM
    
    # Products
    product_candidates: List[Dict[str, Any]] # Candidates found in THIS turn
    current_proposal: Optional[List[Dict[str, Any]]] # [NEW] Active Proposal (Persistent)
    rejected_proposals: List[str] # [NEW] Blacklist
    
    # Output Generation
    generated_reasoning: Optional[str]
    agent_script: Optional[str] # Final script to speak
    next_actions: List[Dict[str, Any]] # Full action plan
