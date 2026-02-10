from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI AI Service"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/ai/api/v1"
    OPENAI_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str
    QDRANT_DENSE_EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    QDRANT_SPARSE_EMBEDDING_MODEL: str = "Qdrant/bm25"

    # Spring Backend Configuration
    SPRING_API_KEY: str
    SPRING_API_URL: str = "http://localhost:8080/api/v1/calls/end"
    SPRING_CUSTOMER_API_URL: str = "http://localhost:8080/api/v1/customers/search"

    # LLM Configuration
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "https://api.csnavigator.cloud",
        "https://www.csnavigator.cloud",
        "http://127.0.0.1:5173"
    ]
    
    # Simulation Configuration
    SIMULATION_TARGET_URI: str = "ws://127.0.0.1:8000/ai/api/v1/agent/check"

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
