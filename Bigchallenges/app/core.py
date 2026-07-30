from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings_(BaseSettings):

    DB_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    OPENROUTER_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings_()