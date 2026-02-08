from pydantic import BaseModel
from typing import Optional


class RPPersona(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    desc: Optional[str] = None
    tone: Optional[str] = None
    difficulty: Optional[str] = None


class RPChatRequest(BaseModel):
    session_id: str
    message: str
    persona: Optional[RPPersona] = None
    start: Optional[bool] = False


class RPChatResponse(BaseModel):
    session_id: str
    speaker: str
    message: str
    understanding_level: int
    ready_to_close: bool
