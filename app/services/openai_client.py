from typing import Any

from openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError
from app.models.chat import HistoryMessage
from app.services.prompt_builder import build_phase1_input, build_phase1_instructions


class OpenAIChatService:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        settings.require_openai_api_key()
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.openai_api_key)

    def generate_reply(self, message: str, history: list[HistoryMessage]) -> str:
        instructions = build_phase1_instructions()
        input_items = build_phase1_input(message=message, history=history)

        try:
            response = self.client.responses.create(
                model=self.settings.openai_model,
                instructions=instructions,
                input=input_items,
                max_output_tokens=self.settings.openai_max_output_tokens,
                temperature=0.4,
            )
        except Exception as exc:  # pragma: no cover - exercised via API tests
            raise UpstreamServiceError("OpenAI request failed.") from exc

        reply = self._extract_output_text(response)
        if not reply:
            raise UpstreamServiceError("OpenAI returned an empty response.")
        return reply

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text.strip()
        return ""
