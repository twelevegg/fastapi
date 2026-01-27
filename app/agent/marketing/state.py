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
    call_stage: str # "verification", "consent", "problem_solving", "offer_discussion", "closing"
    marketing_needed: bool
    marketing_type: Literal["none", "support_only", "upsell", "retention", "hybrid"]
    
    # Retrieval
    search_query: Optional[str]
    retrieved_items: List[Dict[str, Any]] # Raw items from Qdrant
    context_text: Optional[str] # Formatted string for LLM
    
    # Products
    product_candidates: List[Dict[str, Any]]
    
    # Output Generation
    generated_reasoning: Optional[str]
    agent_script: Optional[str] # Final script to speak
    next_actions: List[Dict[str, Any]] # Full action plan
