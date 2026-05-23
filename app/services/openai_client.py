from typing import Any

from openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError
from app.models.chat import HistoryMessage
from app.models.extractor import MemoryExtractionResult
from app.models.knowledge import KnowledgeCard
from app.models.memory import MemoryRecord
from app.services.prompt_builder import (
    build_assistant_instructions,
    build_memory_extractor_input,
    build_memory_extractor_instructions,
    build_phase1_input,
)


class OpenAIResponseService:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        settings.require_openai_api_key()
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.openai_api_key)

    def generate_assistant_reply(
        self,
        message: str,
        history: list[HistoryMessage],
        relevant_memories: list[MemoryRecord],
        relevant_knowledge_cards: list[KnowledgeCard],
    ) -> str:
        instructions = build_assistant_instructions(
            relevant_memories,
            relevant_knowledge_cards,
        )
        input_items = build_phase1_input(message=message, history=history)

        try:
            response = self.client.responses.create(
                model=self.settings.openai_model,
                instructions=instructions,
                input=input_items,
                max_output_tokens=self.settings.openai_max_output_tokens,
                temperature=0.4,
            )
        except Exception as exc:  # pragma: no cover
            raise UpstreamServiceError("OpenAI request failed.") from exc

        reply = self._extract_output_text(response)
        if not reply:
            raise UpstreamServiceError("OpenAI returned an empty response.")
        return reply

    def extract_memory_updates(
        self,
        user_message: str,
        assistant_reply: str,
        relevant_memories: list[MemoryRecord],
    ) -> MemoryExtractionResult:
        instructions = build_memory_extractor_instructions()
        extractor_input = build_memory_extractor_input(
            user_message=user_message,
            assistant_reply=assistant_reply,
            relevant_memories=relevant_memories,
        )

        try:
            response = self.client.responses.parse(
                model=self.settings.openai_extractor_model,
                instructions=instructions,
                input=extractor_input,
                text_format=MemoryExtractionResult,
            )
        except Exception as exc:  # pragma: no cover
            raise UpstreamServiceError("Memory extraction request failed.") from exc

        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, MemoryExtractionResult):
            raise UpstreamServiceError("Memory extraction returned invalid structured output.")
        return parsed

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text.strip()
        return ""
