import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.exceptions import MissingConfigurationError


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_extractor_model: str
    openai_max_output_tokens: int
    database_path: str
    app_env: str
    enable_debug_metadata: bool
    knowledge_cards_path: str
    default_user_id: str
    default_timezone: str
    telegram_bot_token: str | None
    telegram_mode: str

    @classmethod
    def from_env(cls) -> "Settings":
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=model,
            openai_extractor_model=os.getenv("OPENAI_EXTRACTOR_MODEL", model),
            openai_max_output_tokens=350,
            database_path=os.getenv("DATABASE_PATH", "sleep_assistant.db"),
            app_env=os.getenv("APP_ENV", "production"),
            enable_debug_metadata=env_flag("ENABLE_DEBUG_METADATA", default=False),
            knowledge_cards_path=os.getenv(
                "KNOWLEDGE_CARDS_PATH", "app/data/knowledge_cards.json"
            ),
            default_user_id="default_user",
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_mode=os.getenv("TELEGRAM_MODE", "polling"),
        )

    def require_openai_api_key(self) -> None:
        if self.openai_api_key:
            return
        raise MissingConfigurationError(
            "OPENAI_API_KEY is required to start the sleep assistant service."
        )

    @property
    def debug_metadata_allowed(self) -> bool:
        return self.enable_debug_metadata or self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
