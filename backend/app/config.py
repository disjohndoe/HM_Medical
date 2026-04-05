from __future__ import annotations

import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRET_PATTERNS = [
    "dev-secret",
    "change-me",
    "not-for-production",
    "secret-key",
    "changeme",
    "default-secret",
    "example",
    "test-secret",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_VERSION: str = "0.1.0"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/medical_mvp"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Security — JWT_SECRET_KEY is REQUIRED, no insecure default
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # File uploads
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # CEZIH Integration
    CEZIH_MODE: str = "mock"  # "mock" or "real"
    CEZIH_OAUTH2_URL: str = ""  # Keycloak token endpoint (VPN: certsso2, public: certpubsso)
    CEZIH_CLIENT_ID: str = ""
    CEZIH_CLIENT_SECRET: str = ""
    CEZIH_FHIR_BASE_URL: str = ""  # e.g. https://certws2.cezih.hr:8443 (clinical FHIR)
    CEZIH_FHIR_AUX_URL: str = ""  # e.g. https://certws2.cezih.hr:9443 (terminology, mCSD, OID, notifications)
    CEZIH_SIGNING_URL: str = ""  # Remote signing endpoint (certpubws.cezih.hr)
    CEZIH_SIGNING_OAUTH2_URL: str = ""  # Public Keycloak for signing (certpubsso.cezih.hr)
    CEZIH_TIMEOUT: int = 30
    CEZIH_RETRY_ATTEMPTS: int = 3
    CEZIH_ORG_CODE: str = ""  # HZZO sifra zdravstvene organizacije
    CEZIH_OID: str = ""  # OID informacijskog sustava (urn:oid:...)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def db_echo(self) -> bool:
        return self.APP_DEBUG and not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


def _validate_jwt_secret(secret: str) -> None:
    """Validate JWT secret strength. Only called in production."""
    secret_lower = secret.lower()
    for pattern in _WEAK_SECRET_PATTERNS:
        if pattern in secret_lower:
            print(
                f"FATAL: JWT_SECRET_KEY contains weak pattern '{pattern}'. "
                "Generate a strong secret with: openssl rand -hex 32",
                file=sys.stderr,
            )
            sys.exit(1)
    if len(secret) < 32:
        print(
            "FATAL: JWT_SECRET_KEY must be at least 32 characters. "
            "Generate with: openssl rand -hex 32",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(set(secret)) < 8:
        print(
            "FATAL: JWT_SECRET_KEY has insufficient entropy.",
            file=sys.stderr,
        )
        sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production:
        _validate_jwt_secret(s.JWT_SECRET_KEY)
    return s


settings = get_settings()
