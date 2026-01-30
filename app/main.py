from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.config import settings

# Ensure environment variables are set for legacy modules depending on os.environ
import os
if settings.QDRANT_URL:
    os.environ["QDRANT_URL"] = settings.QDRANT_URL
if settings.QDRANT_API_KEY:
    os.environ["QDRANT_API_KEY"] = settings.QDRANT_API_KEY
if settings.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
    # Proxy to LLM_* for session.py compatibility
    os.environ["LLM_API_KEY"] = settings.OPENAI_API_KEY

# Ensure LLM Base/Model are available for session.py
if settings.LLM_BASE_URL:
    os.environ["LLM_BASE_URL"] = settings.LLM_BASE_URL
if settings.LLM_MODEL:
    os.environ["LLM_MODEL"] = settings.LLM_MODEL

# LLM Config from settings (if defined in .env but not in pydantic model, access via os.getenv or add to model)
# But wait, config.py didn't have LLM_BASE_URL. Let's check config.py again or just use os.environ direct read if pydantic didn't load it.
# Actually, best to just read from .env directly here or assume load_dotenv() happened?
# FastAPI's config.py uses pydantic-settings which loads .env.
# If keys are missing in Settings class, they are ignored.
# Let's verify config.py content first to see if LLM_BASE_URL is there.
# If not, I should add them to Settings or read raw os.environ after load_dotenv.
# Since I can't easily change Settings without import errors, I will trust that load_dotenv works if I call it, 
# OR I can just hardcode the injection if I see them in the .env file view.

# Actually, I'll just check if they exist in valid env var locations or inject defaults.
# The user's .env had LLM_BASE_URL and LLM_MODEL.
# Pydantic Settings might NOT have loaded them if they weren't in the class.
# So I should use dotenv directly or add to Settings.
# Adding to Settings is cleaner. Let's check config.py.

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS 임시 설정
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite
        "http://localhost:3000"   # CRA
        ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI AI Service"}


@app.get("/health")
async def health():
    return {"status": "ok"}
