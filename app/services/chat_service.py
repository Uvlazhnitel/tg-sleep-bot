import logging
import re

from app.core.exceptions import UpstreamServiceError
from app.models.chat import ChatDebugMetadata, ChatResponse, HistoryMessage
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
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
        memory_transparency_service: MemoryTransparencyService,
        debug_metadata_allowed: bool = False,
    ) -> None:
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.openai_service = openai_service
        self.safety_classifier = safety_classifier
        self.memory_transparency_service = memory_transparency_service
        self.debug_metadata_allowed = debug_metadata_allowed

    def generate_reply(
        self,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None = None,
        include_debug: bool = False,
    ) -> ChatResponse:
        session_key = self.memory_transparency_service.normalize_session_id(session_id)
        memory_enabled_for_session = self.memory_transparency_service.is_memory_enabled_for_session(
            session_key
        )

        pending_reply = self._handle_pending_confirmation(message, session_key)
        if pending_reply is not None:
            return ChatResponse(reply=pending_reply)

        intent_reply = self._handle_memory_intent(
            message,
            session_key,
            memory_enabled=memory_enabled_for_session,
        )
        if intent_reply is not None:
            return ChatResponse(reply=intent_reply)

        feedback_reply = self._handle_feedback_intent(
            message,
            history,
            memory_enabled=memory_enabled_for_session,
        )
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
        self.memory_transparency_service.store_advice_trace(
            session_id=session_key,
            user_message=message,
            assistant_reply=reply,
            source_memory_ids=[memory.id for memory in relevant_memories],
            knowledge_card_ids=[card.id for card in relevant_knowledge_cards],
            safety_category=safety_classification.category,
        )

        if memory_enabled_for_session and safety_classification.category != "D":
            try:
                extraction = self.openai_service.extract_memory_updates(
                    user_message=message,
                    assistant_reply=reply,
                    relevant_memories=relevant_memories,
                )
                if extraction.skip_memory:
                    extraction = self.memory_service.validate_extraction_result(extraction)
                else:
                    extraction = self.memory_service.restrict_extraction_for_safety(
                        extraction,
                        safety_classification,
                    )
                    extraction, sensitive_extraction = self.memory_transparency_service.split_sensitive_updates(
                        extraction
                    )
                    validated = self.memory_service.validate_extraction_result(extraction)
                    self.memory_service.apply_memory_updates(validated)
                    if sensitive_extraction is not None and sensitive_extraction.memory_updates:
                        pending = self.memory_transparency_service.create_pending_confirmation(
                            session_key,
                            sensitive_extraction,
                        )
                        return ChatResponse(reply=f"{reply}\n\n{pending.prompt_text}")
                    extraction = validated
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

    def _handle_memory_intent(
        self,
        message: str,
        session_id: str,
        memory_enabled: bool,
    ) -> str | None:
        intent = self.memory_transparency_service.detect_intent(message)
        if intent.intent_type == "show_memory":
            return self.memory_transparency_service.summarize_memories_for_user()
        if intent.intent_type == "delete_memory" and intent.payload is not None:
            return self.memory_transparency_service.handle_delete_request(intent.payload)
        if intent.intent_type == "update_memory":
            if not memory_enabled:
                return "Okay — memory is off for this session, so I won't save that change."
            return self.memory_transparency_service.handle_update_request(
                intent.payload or message
            )
        if intent.intent_type == "explain_advice":
            return self.memory_transparency_service.explain_last_advice(session_id)
        if intent.intent_type == "disable_memory_for_turn":
            return "Okay — I won't save anything from this exchange."
        if intent.intent_type == "disable_memory_for_session":
            self.memory_transparency_service.set_memory_disabled_for_session(
                session_id,
                enabled=False,
            )
            return "Okay — I turned memory off for this session."
        if intent.intent_type == "enable_memory_for_session":
            self.memory_transparency_service.set_memory_disabled_for_session(
                session_id,
                enabled=True,
            )
            return "Okay — memory is back on for this session."

        remember_request = self.memory_service.personalization.infer_preference_or_constraint(
            message
        )
        if remember_request is not None:
            if not memory_enabled:
                return "Okay — memory is off for this session, so I won't save that."
            memory = self.memory_service.create_memory(remember_request)
            return f"I'll remember that: {memory.content}"

        return None

    def _handle_feedback_intent(
        self,
        message: str,
        history: list[HistoryMessage],
        memory_enabled: bool,
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
            if not memory_enabled:
                return "Okay — memory is off for this session, so I won't save that feedback."
            intervention = self._infer_recent_intervention(history)
            if intervention is None:
                return "What part helped, so I can remember the useful bit?"
            memory = self.memory_service.record_intervention_feedback(intervention, "helped")
            return f"Good to know. I'll remember that this helped: {memory.content}"

        if "that didn't work" in lowered or "that did not work" in lowered:
            if not memory_enabled:
                return "Okay — memory is off for this session, so I won't save that feedback."
            intervention = self._infer_recent_intervention(history)
            if intervention is None:
                return "What part did not work, so I can avoid repeating the wrong thing?"
            memory = self.memory_service.record_intervention_feedback(intervention, "did_not_help")
            return f"Thanks, I'll avoid leaning on that next time: {memory.content}"

        if lowered.startswith("actually") or "that's wrong" in lowered or "that is wrong" in lowered:
            if not memory_enabled:
                return "Okay — memory is off for this session, so I won't save that correction."
            memories = self.memory_service.get_relevant_memories(message)
            best = self.memory_service.personalization.find_best_memory_match(message, memories)
            if best is None:
                return "Which previous idea or memory should I correct?"
            updated = self.memory_service.apply_feedback(best.id, "wrong")
            if updated.is_archived:
                return f"Thanks for correcting me. I archived that memory: {updated.content}"
            return f"Thanks for correcting me. I'll treat that as less reliable: {updated.content}"

        return None

    def _handle_pending_confirmation(
        self,
        message: str,
        session_id: str,
    ) -> str | None:
        pending = self.memory_transparency_service.get_pending_confirmation(session_id)
        if pending is None:
            return None

        lowered = message.strip().lower()
        if lowered in {"yes", "yes remember that", "yes save that", "save it", "remember it"}:
            return self.memory_transparency_service.resolve_pending_confirmation(
                session_id,
                accept=True,
            )
        if lowered in {
            "no",
            "no do not save that",
            "don't save that",
            "dont save that",
            "no thanks",
        }:
            return self.memory_transparency_service.resolve_pending_confirmation(
                session_id,
                accept=False,
            )
        return None

    @staticmethod
    def _infer_recent_intervention(history: list[HistoryMessage]) -> str | None:
        for item in reversed(history):
            if item.role == "assistant":
                return item.content
        return None
