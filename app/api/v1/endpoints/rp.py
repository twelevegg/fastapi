from fastapi import APIRouter
from app.schemas.rp import RPChatRequest, RPChatResponse
from app.services.rp_service import handle_agent_message

router = APIRouter()


@router.post("/rp", response_model=RPChatResponse)
async def rp_chat(req: RPChatRequest):
    print(f"[RP] Request received for session: {req.session_id}, msg: {req.message}")
    persona = req.persona.model_dump() if req.persona else None

    state = await handle_agent_message(
        session_id=req.session_id,
        message=req.message,
        persona=persona,
        start=bool(req.start),
    )

    # [DEBUG]
    # print(f"[RP] Final State keys: {state.keys()}")
    if not state.get("messages"):
        print("[RP] ERROR: No messages in state!")
        # 예외를 던지거나 기본값 처리

    last_msg = state["messages"][-1]
    print(f"[RP] Last message role: {last_msg.type}, Content: {last_msg.content}")

    return RPChatResponse(
        session_id=req.session_id,
        speaker="customer",
        message=last_msg.content,
        understanding_level=state["understanding_level"],
        ready_to_close=state["ready_to_close"],
    )
