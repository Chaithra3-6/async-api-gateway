"""Application settings, loaded from environment variables (or a .env file).

pydantic-settings validates types and gives one typed object to import.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- auth ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # demo credentials for the /auth/token endpoint (replace with a real user store)
    demo_username: str = "demo"
    demo_password: str = "demo-password"

    # --- upstreams (three services the gateway aggregates) ---
    user_service_url: str = "http://localhost:9001"
    orders_service_url: str = "http://localhost:9001"
    recommendations_service_url: str = "http://localhost:9001"
    upstream_timeout_seconds: float = 3.0

    # --- redis (cache + rate limiting) ---
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 30

    # --- mongodb (append-only request audit log) ---
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "gateway"

    # --- rate limiting ---
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # --- resilience ---
    retry_attempts: int = 2
    retry_base_delay: float = 0.2
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0


settings = Settings()
