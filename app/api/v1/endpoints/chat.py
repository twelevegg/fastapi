from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import openai_service
from app.core.exceptions import OpenAIException

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        reply = await openai_service.get_chat_response(request.message, request.model)
        return ChatResponse(reply=reply)
    except OpenAIException as e:
        raise HTTPException(status_code=500, detail=str(e))
