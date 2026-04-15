from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-5-mini"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    vertex_user_name: str = "Rehan"
    vertex_user_location: str = "London, UK"

    allowed_device_ids: list[str] = []

    # MCP server API keys (optional -- servers only start if key is set)
    openweathermap_api_key: str = ""
    tavily_api_key: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"
    spotify_refresh_token: str = ""

    whatsapp_enabled: bool = False
    whatsapp_bridge_url: str = "http://localhost:9777"

    # FCM: path to Firebase service account JSON (or set GOOGLE_APPLICATION_CREDENTIALS)
    firebase_credentials_path: str = ""

    google_enabled: bool = False
    google_maps_api_key: str = ""

    # TTS: use Google Cloud (Indian English/Hindi) when True + GOOGLE_APPLICATION_CREDENTIALS set
    tts_use_google: bool = True
    github_token: str = ""
    github_username: str = ""

    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # Ignore unknown env vars (e.g. GOOGLE_APPLICATION_CREDENTIALS)
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
