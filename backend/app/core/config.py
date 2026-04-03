from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )
    
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
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    
    # LLM
    LLM_PROVIDER: str = "qwen"
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "qwen-plus"
    
    # Chroma
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    
    # Knowledge
    KNOWLEDGE_DIR: str = "./knowledge"
    
    # Memory
    MAX_CONTEXT_MESSAGES: int = 10
    COMPRESSION_THRESHOLD: int = 12  # 轮次
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",") if origin.strip()]


settings = Settings()
