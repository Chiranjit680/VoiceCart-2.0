from typing import Optional

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    database_url:str
    database_hostname: str
    database_port: str
    database_username: str
    database_password: str
    database_name: str
    GEMINI_API_KEY: str

    # Long-term memory service (longterm_memory/). Without a key, the /memories routes answer 503.
    memory_service_url: str = "http://127.0.0.1:8005"
    memory_service_key: Optional[str] = None

    # Voice chat sessions (see routers/chat.py)
    chat_resume_minutes: int = 10  # reconnecting this soon after a disconnect continues the same conversation
    chat_idle_minutes: int = 30  # a session with no activity this long is closed
    chat_retention_days: int = 30  # sessions older than this are deleted, with their transcripts and agent state

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # The root .env is shared with other services (redis, STT, agent URLs), so skip keys not declared here.
        extra = "ignore"
        

settings = Settings()