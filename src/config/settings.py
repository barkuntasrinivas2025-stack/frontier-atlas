from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = 'development'
    log_level: str = 'INFO'
    database_url: str = 'postgresql+asyncpg://frontier:frontier_dev_password@localhost:55432/frontier_atlas'
    redis_url: str = 'redis://localhost:6379/0'
    crawler_concurrency: int = 20
    llm_concurrency: int = 10
    http_timeout_seconds: int = 30
    github_token: str = ''
    gemini_api_key: str = ''
    groq_api_key: str = ''
    deepseek_api_key: str = ''
    google_sheet_id: str = ''
    google_service_account_file: str = 'credentials.json'
    product_hunt_token: str = ''
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', env_prefix='FA_', extra='ignore')

@lru_cache
def get_settings() -> Settings:
    return Settings()
