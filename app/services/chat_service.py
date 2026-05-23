import logging
import re

from app.core.exceptions import UpstreamServiceError
from app.models.chat import ChatDebugMetadata, ChatResponse, HistoryMessage
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService
from app.services.openai_client import OpenAIResponseService
from app.services.safety_classifier import SafetyClassifierService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        openai_service: OpenAIResponseService,
        safety_classifier: SafetyClassifierService,
        debug_metadata_allowed: bool = False,
    ) -> None:
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.openai_service = openai_service
        self.safety_classifier = safety_classifier
        self.debug_metadata_allowed = debug_metadata_allowed

    def generate_reply(
        self,
        message: str,
        history: list[HistoryMessage],
        include_debug: bool = False,
    ) -> ChatResponse:
        intent_reply = self._handle_memory_intent(message)
        if intent_reply is not None:
            return ChatResponse(reply=intent_reply)

        feedback_reply = self._handle_feedback_intent(message, history)
        if feedback_reply is not None:
            return ChatResponse(reply=feedback_reply)

        relevant_memories = self.memory_service.get_relevant_memories(message)
        safety_classification = self.safety_classifier.classify(
            message,
            history,
            relevant_memories,
        )
        personalization_context = self.memory_service.get_personalization_context(message)
        relevant_knowledge_cards = self.knowledge_service.get_relevant_knowledge_cards(
            message,
            relevant_memories,
            safety_red_flag_types=[flag.type for flag in safety_classification.red_flags],
        )
        reply = self.openai_service.generate_assistant_reply(
            message=message,
            history=history,
            relevant_memories=relevant_memories,
            relevant_knowledge_cards=relevant_knowledge_cards,
            personalization_context=personalization_context,
            safety_classification=safety_classification,
        )
        self.memory_service.mark_memories_used(relevant_memories)

        if safety_classification.category != "D":
            try:
                extraction = self.openai_service.extract_memory_updates(
                    user_message=message,
                    assistant_reply=reply,
                    relevant_memories=relevant_memories,
                )
                extraction = self.memory_service.restrict_extraction_for_safety(
                    extraction,
                    safety_classification,
                )
                validated = self.memory_service.validate_extraction_result(extraction)
                self.memory_service.apply_memory_updates(validated)
            except UpstreamServiceError as exc:
                logger.warning("Memory extraction skipped: %s", exc)

        debug = None
        if include_debug and self.debug_metadata_allowed:
            debug = ChatDebugMetadata(
                memory_ids=[memory.id for memory in relevant_memories],
                knowledge_card_ids=[card.id for card in relevant_knowledge_cards],
                personalization_context=personalization_context,
                safety_category=safety_classification.category,
                safety_red_flag_types=[
                    flag.type for flag in safety_classification.red_flags
                ],
                should_prioritize_immediate_safety=safety_classification.should_prioritize_immediate_safety,
            )

        return ChatResponse(reply=reply, debug=debug)

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

        remember_request = self.memory_service.personalization.infer_preference_or_constraint(
            message
        )
        if remember_request is not None:
            memory = self.memory_service.create_memory(remember_request)
            return f"I'll remember that: {memory.content}"

        return None

    def _handle_feedback_intent(
        self,
        message: str,
        history: list[HistoryMessage],
    ) -> str | None:
        lowered = message.strip().lower()
        if lowered in {"don't remember that", "dont remember that"}:
            memories = self.memory_service.list_memories(include_archived=False)
            best = self.memory_service.personalization.find_best_memory_match(
                history[-1].content if history else message,
                memories,
            )
            if best is None:
                return "Tell me what you want me to forget, and I'll remove it."
            archived = self.memory_service.archive_memory(best.id)
            return f"Okay, I won't keep this memory: {archived.content}"

        if "that helped" in lowered:
            intervention = self._infer_recent_intervention(history)
            if intervention is None:
                return "What part helped, so I can remember the useful bit?"
            memory = self.memory_service.record_intervention_feedback(intervention, "helped")
            return f"Good to know. I'll remember that this helped: {memory.content}"

        if "that didn't work" in lowered or "that did not work" in lowered:
            intervention = self._infer_recent_intervention(history)
            if intervention is None:
                return "What part did not work, so I can avoid repeating the wrong thing?"
            memory = self.memory_service.record_intervention_feedback(intervention, "did_not_help")
            return f"Thanks, I'll avoid leaning on that next time: {memory.content}"

        if lowered.startswith("actually") or "that's wrong" in lowered or "that is wrong" in lowered:
            memories = self.memory_service.get_relevant_memories(message)
            best = self.memory_service.personalization.find_best_memory_match(message, memories)
            if best is None:
                return "Which previous idea or memory should I correct?"
            updated = self.memory_service.apply_feedback(best.id, "wrong")
            if updated.is_archived:
                return f"Thanks for correcting me. I archived that memory: {updated.content}"
            return f"Thanks for correcting me. I'll treat that as less reliable: {updated.content}"

        return None

    @staticmethod
    def _infer_recent_intervention(history: list[HistoryMessage]) -> str | None:
        for item in reversed(history):
            if item.role == "assistant":
                return item.content
        return None
