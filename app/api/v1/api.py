from fastapi import APIRouter
from app.api.v1.endpoints import chat, stt, agent, rp, qa, edu

api_router = APIRouter()
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(stt.router, tags=["stt"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(rp.router, tags=["rp"])         #rp 라우팅
api_router.include_router(qa.router, tags=["qa"])         #/qa/report
api_router.include_router(edu.router, prefix="/edu", tags=["edu"])