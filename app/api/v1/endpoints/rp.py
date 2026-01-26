from fastapi import APIRouter
from app.schemas.rp import RPChatRequest, RPChatResponse
from app.services.rp_service import handle_agent_message

router = APIRouter()

@router.post("/rp", response_model=RPChatResponse)
async def rp_chat(req: RPChatRequest):
    state = await handle_agent_message(
        session_id=req.session_id,
        message=req.message,
    )

    last_msg = state["messages"][-1]

    return RPChatResponse(
        session_id=req.session_id,
        speaker="customer",
        message=last_msg.content,
        understanding_level=state["understanding_level"],
        ready_to_close=state["ready_to_close"],
        qa_result=state["qa_result"],
    )