import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.exceptions import MissingConfigurationError


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_extractor_model: str
    openai_max_output_tokens: int
    database_path: str
    default_user_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=model,
            openai_extractor_model=os.getenv("OPENAI_EXTRACTOR_MODEL", model),
            openai_max_output_tokens=350,
            database_path=os.getenv("DATABASE_PATH", "sleep_assistant.db"),
            default_user_id="default_user",
        )

    def require_openai_api_key(self) -> None:
        if self.openai_api_key:
            return
        raise MissingConfigurationError(
            "OPENAI_API_KEY is required to start the sleep assistant service."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
