import asyncio
from typing import Dict, Any, Optional, List
from app.agent.marketing.session import build_session, MarketingSession
from app.agent.marketing.buffer import StreamBuffer

class MarketingConsumer:
    """
    Consumer class to handle incoming JSON packets from external STT systems.
    Managed sessions and buffering internally.
    """
    def __init__(self):
        # Map: call_id -> MarketingSession
        self.sessions: Dict[str, MarketingSession] = {}
        # Map: call_id -> StreamBuffer
        self.buffers: Dict[str, StreamBuffer] = {}

    def _get_or_create_resources(self, call_id: str, customer_number: Optional[str] = None):
        if call_id not in self.sessions:
            print(f"[Consumer] Creating new session for {call_id}")
            # In a real scenario, you might want to load customer info from DB based on customer_number
            # Here we initialize with defaults or passed info
            self.sessions[call_id] = build_session(customer_id=None, phone=customer_number)
            self.buffers[call_id] = StreamBuffer(min_length=5)
        return self.sessions[call_id], self.buffers[call_id]

    async def consume(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests a JSON packet, buffers the text, and runs analysis if a sentence is complete.

        Expected packet keys (flexible):
        - call_id (required): Session Identifier
        - text / transcript / content (one required): The STT text chunk
        - customer_number (optional): Customer phone number
        """
        # 1. Extract Call ID
        call_id = packet.get("call_id")
        if not call_id:
            return {"status": "error", "message": "Missing 'call_id' in packet."}

        # 2. Extract Text (Try multiple common keys)
        text = packet.get("text") or packet.get("transcript") or packet.get("content")
        
        # 3. Get Resources
        customer_number = packet.get("customer_number")
        session, buffer = self._get_or_create_resources(call_id, customer_number)

        # 4. Buffer Logic
        if not text:
            # Maybe it's a control event (e.g. hangup)?
            # For now, just ignore non-text packets
            return {"status": "ignored", "message": "No text found in packet."}
        
        # Add to buffer
        buffer.add_chunk(str(text))
        
        # [Fix] Flush immediately to prevent waiting for punctuation (Instant Response)
        sentence = buffer.force_flush()
        
        # [NEW] Speculative Execution Check
        # Even if sentence is not complete, check for triggers
        trigger = buffer.check_prefetch_trigger(str(text))
        if trigger:
            # Fire and forget (don't await to avoid blocking buffer)
            asyncio.create_task(session.prefetch(trigger))
        
        if not sentence:
            return {"status": "buffered", "message": "Fragment buffered."}

        print(f"[Consumer] Processing refined sentence: {sentence}")

        # 5. Process Complete Sentence
        session.add_turn(speaker="customer", transcript=sentence)
        
        # Async Analysis
        result = await session.step()

        # 6. Format Result
        decision = result.get("decision", {})
        next_actions = decision.get("next_actions", [])
        script = next_actions[0].get("agent_script", {}).get("opening") if next_actions else None

        return {
            "status": "processed",
            "call_id": call_id,
            "is_marketing_needed": result.get("marketing_needed", False),
            "marketing_type": result.get("marketing_type", "none"),
            "agent_script": script,
            "full_result": result
        }

    def flush_session(self, call_id: str) -> Dict[str, Any]:
        """
        Force flush buffer for a specific session (e.g. on call end).
        """
        if call_id not in self.sessions:
             return {"status": "error", "message": "Session not found."}
             
        buffer = self.buffers[call_id]
        session = self.sessions[call_id]
        
        remaining_text = buffer.force_flush()
        if remaining_text:
             # Sync run or just return raw? 
             # Since this might be called from synchronous context or cleanup, 
             # proper async handling is needed if we want to run step().
             # For now, simply indicating there was text. 
             # In a full impl, you'd run one last step().
             pass
        
        # Cleanup
        del self.sessions[call_id]
        del self.buffers[call_id]
        
        return {"status": "flushed_and_closed", "call_id": call_id}
