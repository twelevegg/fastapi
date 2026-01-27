from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI AI Service"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    OPENAI_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str
    Qdrant_DENSE_EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    QDRANT_SPARSE_EMBEDDING_MODEL: str = "Qdrant/bm25"

    # LLM Configuration
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
