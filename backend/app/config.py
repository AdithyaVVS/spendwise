from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24  # tokens last 24 hours

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
