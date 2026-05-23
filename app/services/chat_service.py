import logging
import re

from app.core.exceptions import UpstreamServiceError
from app.models.chat import HistoryMessage
from app.models.memory import MemoryRecord
from app.services.memory_service import MemoryService
from app.services.openai_client import OpenAIResponseService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        memory_service: MemoryService,
        openai_service: OpenAIResponseService,
    ) -> None:
        self.memory_service = memory_service
        self.openai_service = openai_service

    def generate_reply(self, message: str, history: list[HistoryMessage]) -> str:
        intent_reply = self._handle_memory_intent(message)
        if intent_reply is not None:
            return intent_reply

        relevant_memories = self.memory_service.get_relevant_memories(message)
        reply = self.openai_service.generate_assistant_reply(
            message=message,
            history=history,
            relevant_memories=relevant_memories,
        )
        self.memory_service.mark_memories_used(relevant_memories)

        try:
            extraction = self.openai_service.extract_memory_updates(
                user_message=message,
                assistant_reply=reply,
                relevant_memories=relevant_memories,
            )
            validated = self.memory_service.validate_extraction_result(extraction)
            self.memory_service.apply_memory_updates(validated)
        except UpstreamServiceError as exc:
            logger.warning("Memory extraction skipped: %s", exc)

        return reply

    def _handle_memory_intent(self, message: str) -> str | None:
        lowered = message.strip().lower()
        if "what do you remember about me" in lowered or lowered in {"/memory", "show memory"}:
            return self.memory_service.render_memory_summary()

        forget_match = re.match(r"^(forget(?: that)?)(?P<content>.+)$", lowered)
        if forget_match:
            archived = self.memory_service.archive_by_text(forget_match.group("content"))
            if archived is None:
                return "I could not confidently find a matching memory to forget."
            return f"I forgot this memory: {archived.content}"

        goal_match = re.search(
            r"(?:change|set) my wake[ -]?up goal to (?P<time>\d{1,2}:\d{2})",
            lowered,
        )
        if goal_match:
            memory = self.memory_service.update_goal(goal_match.group("time"))
            return f"Updated your wake-up goal: {memory.content}"

        return None
