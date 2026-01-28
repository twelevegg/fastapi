from pydantic import BaseModel

class RPChatRequest(BaseModel):
    session_id: str
    message: str


class RPChatResponse(BaseModel):
    session_id: str
    speaker: str
    message: str
    understanding_level: int
    ready_to_close: bool