from fastapi import APIRouter
from app.api.v1.endpoints import chat, stt, agent, rp, guidance

api_router = APIRouter()
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(stt.router, tags=["stt"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(rp.router, tags=["rp"])         #rp 라우팅
api_router.include_router(guidance.router, tags=["guidance"]) # guidance ws 라우팅