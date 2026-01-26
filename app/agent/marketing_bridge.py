import sys
import os
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# [Critical] Add project root to sys.path to import src.consumer
# fastapi-main/app/agent -> .../fastapi-main -> .../project_root
# We need to jump up 3 levels? No, project root is parent of fastapi-main
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.consumer import MarketingConsumer

# Singleton Instance
_consumer = None

def get_marketing_consumer():
    global _consumer
    if _consumer is None:
        _consumer = MarketingConsumer()
    return _consumer

async def process_marketing_turn(transcript: str, turn_id: int):
    """
    Bridge function: Calls AI Agent's consume method
    """
    consumer = get_marketing_consumer()
    # Mocking a packet structure expected by consumer.py
    # packet = {"text": transcript, "turn_id": turn_id, ...}
    
    # We need to check consumer.consume signature
    # It expects: packet: Dict[str, Any]
    
    packet = {
        "text": transcript,
        "turn_id": turn_id,
        "speaker": "customer", # WebSockets usually send customer speech
        "call_id": "ws_session" # Simplified for now
    }
    
    result = await consumer.consume(packet)
    return result
