import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.exceptions import MissingConfigurationError


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_max_output_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_max_output_tokens=350,
        )

    def require_openai_api_key(self) -> None:
        if self.openai_api_key:
            return
        raise MissingConfigurationError(
            "OPENAI_API_KEY is required to start the Phase 1 chat service."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
