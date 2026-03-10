from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "ServiceBrain"
    APP_ENV: str = "development"
    DEBUG: bool = True
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/servicebrain.db"
    
    # JWT
    SECRET_KEY: str = "servicebrain-demo-secret-key-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    
    # LLM
    LLM_PROVIDER: str = "moonshot"
    LLM_BASE_URL: str = "https://api.moonshot.cn/v1"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "kimi-coding/k2p5"
    
    # Chroma
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    
    # Knowledge
    KNOWLEDGE_DIR: str = "./knowledge"
    
    # Memory
    MAX_CONTEXT_MESSAGES: int = 10
    COMPRESSION_THRESHOLD: int = 12  # 轮次
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
