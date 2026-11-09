"""Application settings loaded from environment variables and the local .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings supplied by the process environment."""

    database_url: str

    # Language model used for answers (any OpenAI-compatible server, e.g. Ollama).
    # Changing the model only needs these values in .env.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "tabayyun-qwen"
    llm_api_key: str = ""
    llm_timeout: float = 300
    # "none" turns off the model's thinking step (much faster on CPU). Leave it empty
    # for providers or models that do not accept the reasoning_effort field.
    llm_reasoning_effort: str = "none"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
