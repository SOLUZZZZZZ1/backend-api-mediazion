from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    allowed_origins: str = "*"
    database_url: str = "sqlite:///./mediazion.db"

    # SMTP (optional)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_tls: bool = True
    mail_from: str = "no-reply@mediazion.eu"
    mail_to: str = "contacto@mediazion.eu"

    # STRIPE
    stripe_secret_key: str | None = None
    stripe_public_key: str | None = None
    stripe_webhook_secret: str | None = None
    statement_descriptor: str = "MEDIAZION"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = ""
        case_sensitive = False

settings = Settings()

def get_allowed_origins() -> list[str]:
    raw = settings.allowed_origins or "*"
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]
