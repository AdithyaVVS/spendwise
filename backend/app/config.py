from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24  # tokens last 24 hours
    production: bool = False
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def secret_must_be_long_in_production(self):
        if self.production and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters when PRODUCTION is true")
        return self


settings = Settings()
