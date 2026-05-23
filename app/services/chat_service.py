import logging
import re

from app.core.exceptions import UpstreamServiceError
from app.models.chat import ChatDebugMetadata, ChatResponse, HistoryMessage
from app.models.insight import InsightPreferenceUpdateRequest
from app.models.reminder import ReminderUpdateRequest
from app.models.settings import UserSettingsUpdateRequest
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
from app.services.integration_service import CalendarService, HealthDataService
from app.services.insight_service import InsightService
from app.services.openai_client import OpenAIResponseService
from app.services.reminder_service import ReminderService
from app.services.safety_classifier import SafetyClassifierService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        openai_service: OpenAIResponseService,
        safety_classifier: SafetyClassifierService,
        memory_transparency_service: MemoryTransparencyService,
        insight_service: InsightService,
        settings_service: SettingsService,
        reminder_service: ReminderService,
        calendar_service: CalendarService,
        health_data_service: HealthDataService,
        debug_metadata_allowed: bool = False,
    ) -> None:
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.openai_service = openai_service
        self.safety_classifier = safety_classifier
        self.memory_transparency_service = memory_transparency_service
        self.insight_service = insight_service
        self.settings_service = settings_service
        self.reminder_service = reminder_service
        self.calendar_service = calendar_service
        self.health_data_service = health_data_service
        self.debug_metadata_allowed = debug_metadata_allowed

    def generate_reply(
        self,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None = None,
        include_debug: bool = False,
        response_language: str | None = None,
    ) -> ChatResponse:
        session_key = self.memory_transparency_service.normalize_session_id(session_id)
        settings = self.settings_service.ensure_feature_defaults()
        session_state = self.memory_transparency_service.get_session_state(session_key)
        if session_state is None:
            memory_enabled_for_session = not self.settings_service.apply_private_mode_default(
                session_has_explicit_state=False
            )
        else:
            memory_enabled_for_session = session_state.memory_enabled

        pending_reply = self._handle_pending_confirmation(message, session_key)
        if pending_reply is not None:
            return ChatResponse(reply=pending_reply)

        settings_reply = self._handle_settings_and_integration_intent(message)
        if settings_reply is not None:
            return ChatResponse(reply=settings_reply)

        reminder_reply = self._handle_reminder_intent(message, settings)
        if reminder_reply is not None:
            return ChatResponse(reply=reminder_reply)

        insight_reply = self._handle_insight_intent(message, history, session_key)
        if insight_reply is not None:
            return ChatResponse(reply=insight_reply)

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
        feature_context = self._build_feature_context(message, settings)
        reply = self.openai_service.generate_assistant_reply(
            message=message,
            history=history,
            relevant_memories=relevant_memories,
            relevant_knowledge_cards=relevant_knowledge_cards,
            personalization_context=personalization_context,
            safety_classification=safety_classification,
            feature_context=feature_context,
            voice_mode=settings.voice_mode,
            response_language=response_language,
        )
        self.memory_service.mark_memories_used(relevant_memories)
        self.memory_transparency_service.store_advice_trace(
            session_id=session_key,
            user_message=message,
            assistant_reply=reply,
            source_memory_ids=[memory.id for memory in relevant_memories],
            knowledge_card_ids=[card.id for card in relevant_knowledge_cards],
            safety_category=safety_classification.category,
            is_private_mode=not memory_enabled_for_session,
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

        proactive_insight_reply = None
        if memory_enabled_for_session:
            try:
                proactive_insight_reply = self.insight_service.maybe_get_proactive_insight_reply(
                    self.memory_service.user_id,
                    message,
                    history,
                    session_key,
                    safety_classification.category,
                )
            except UpstreamServiceError as exc:
                logger.warning("Insight generation skipped: %s", exc)
        if proactive_insight_reply is not None:
            reply = f"{reply}\n\n{proactive_insight_reply}"

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

    def _handle_settings_and_integration_intent(self, message: str) -> str | None:
        lowered = message.strip().lower()
        if lowered in {"turn off reminders.", "turn off reminders"}:
            self.settings_service.disable_feature("reminders")
            return "Okay — reminders are off."
        if lowered in {"what features are enabled?", "what features are enabled"}:
            enabled = self.settings_service.list_enabled_features()
            if not enabled:
                return "No optional features are enabled right now."
            return "Enabled features: " + ", ".join(enabled)
        if lowered.startswith("change my timezone to "):
            timezone = message.split("to", 1)[1].strip().rstrip(".")
            updated = self.settings_service.update_user_settings(
                UserSettingsUpdateRequest(timezone=timezone)
            )
            return f"Okay — I updated your timezone to {updated.timezone}."
        if lowered.startswith("for this week, 09:00 should mean local time in "):
            timezone = message.rsplit("in", 1)[1].strip().rstrip(".")
            from datetime import UTC, datetime, timedelta

            updated = self.settings_service.update_user_settings(
                UserSettingsUpdateRequest(
                    goal_timezone_override=timezone,
                    goal_timezone_override_until=(
                        datetime.now(UTC).replace(microsecond=0) + timedelta(days=7)
                    ).isoformat(),
                )
            )
            return f"Okay — for this week I will treat 09:00 as local time in {updated.goal_timezone_override}."
        if lowered in {"don't use wearable data.", "don't use wearable data"}:
            self.health_data_service.disconnect()
            self.settings_service.disable_feature("health_data")
            return "Okay — I will stop using wearable data."
        if lowered in {"disconnect calendar.", "disconnect calendar"}:
            self.calendar_service.disconnect()
            self.settings_service.disable_feature("calendar")
            return "Okay — I disconnected calendar."
        if lowered in {"use private mode by default.", "use private mode by default"}:
            self.settings_service.update_user_settings(
                UserSettingsUpdateRequest(private_mode_default=True)
            )
            return "Okay — new sessions will default to private mode."
        if lowered.startswith("i am traveling to "):
            destination = message.split("to", 1)[1].strip().rstrip(".")
            return (
                f"Travel can shift how your 09:00 goal feels locally. If you want, you can tell me "
                f'"Change my timezone to {destination}" or set a temporary local-time override.'
            )
        return None

    def _handle_reminder_intent(self, message: str, settings) -> str | None:
        lowered = message.strip().lower()
        if lowered in {"what reminders do i have?", "what reminders do i have"}:
            return self.reminder_service.format_reminders_for_user()
        if lowered in {"turn off evening reminders.", "turn off evening reminders"}:
            for reminder in self.reminder_service.list_reminders():
                if reminder.type == "evening_wind_down":
                    self.reminder_service.update_reminder(
                        reminder.id,
                        ReminderUpdateRequest(active=False),
                    )
            return "Okay — evening reminders are off."
        reminder_request = self.reminder_service.parse_reminder_request(
            message,
            self.settings_service.get_effective_timezone(),
        )
        if reminder_request is not None:
            self.settings_service.enable_feature("reminders")
            reminder = self.reminder_service.create_reminder(reminder_request)
            local_description = f"{reminder.scheduled_time} ({reminder.timezone})"
            return f"Okay — I set that reminder for {local_description}."
        if "set a reminder" in lowered or "reminder" in lowered and "should" in lowered:
            return "I can do that if you want. Tell me the reminder and time, for example: Remind me to start winding down at 23:30."
        return None

    def _build_feature_context(self, message: str, settings) -> str:
        parts: list[str] = [f"Timezone: {self.settings_service.get_effective_timezone()}."]
        lowered = message.lower()
        if settings.calendar_enabled and self._message_needs_calendar(lowered):
            context = self.calendar_service.get_relevant_context(
                self.settings_service.get_effective_timezone()
            )
            if context:
                parts.append(context)
        if settings.health_data_enabled and self._message_needs_health_data(lowered):
            context = self.health_data_service.get_relevant_context(
                self.settings_service.get_effective_timezone()
            )
            if context:
                parts.append(context)
        if settings.reminders_enabled and "reminder" in lowered:
            parts.append(self.reminder_service.format_reminders_for_user())
        return " ".join(parts)

    @staticmethod
    def _message_needs_calendar(message: str) -> bool:
        return any(
            phrase in message
            for phrase in ("nap", "meeting", "calendar", "tomorrow morning", "early obligation", "travel")
        )

    @staticmethod
    def _message_needs_health_data(message: str) -> bool:
        return any(
            phrase in message
            for phrase in ("last night", "wearable", "sleep score", "fitbit", "oura", "garmin", "google fit", "apple health")
        )

    def _handle_insight_intent(
        self,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None,
    ) -> str | None:
        intent = self.insight_service.detect_intent(message)
        user_id = self.memory_service.user_id
        current = self.insight_service.get_latest_actionable_insight()

        if intent.intent_type == "manual_insights":
            return self.insight_service.get_manual_insights(user_id, message, history, session_id)
        if intent.intent_type == "disable_proactive_insights":
            self.settings_service.update_user_settings(
                UserSettingsUpdateRequest(proactive_insights_enabled=False)
            )
            self.insight_service.update_preferences(
                InsightPreferenceUpdateRequest(proactive_insights_enabled=False)
            )
            return "Okay — I will stop giving proactive insights."
        if intent.intent_type == "enable_proactive_insights":
            self.settings_service.update_user_settings(
                UserSettingsUpdateRequest(proactive_insights_enabled=True)
            )
            self.insight_service.update_preferences(
                InsightPreferenceUpdateRequest(proactive_insights_enabled=True)
            )
            return "Okay — proactive insights are back on."
        if current is None:
            if intent.intent_type == "explain_insight":
                explanation = self.memory_transparency_service.explain_last_advice(session_id)
                if explanation.startswith("I do not have enough recent context"):
                    return "I do not have a recent insight to explain right now."
                return explanation
            if intent.intent_type in {
                "dismiss_insight",
                "archive_insight",
                "save_insight_as_pattern",
                "reject_insight",
                "experiment_helped",
                "experiment_failed",
            }:
                return "I do not have a recent insight to apply that to."
            return None
        if intent.intent_type == "dismiss_insight":
            self.insight_service.dismiss_insight(user_id, current.id)
            return "Okay — I dismissed that insight and will not keep resurfacing it."
        if intent.intent_type == "archive_insight":
            self.insight_service.archive_insight(user_id, current.id)
            return "Okay — I forgot that insight."
        if intent.intent_type == "save_insight_as_pattern":
            return self.insight_service.save_insight_as_pattern(user_id, current.id)
        if intent.intent_type == "reject_insight":
            return self.insight_service.handle_rejected_insight(user_id, current.id)
        if intent.intent_type == "experiment_helped":
            return self.insight_service.record_experiment_feedback(user_id, current.id, "helped")
        if intent.intent_type == "experiment_failed":
            return self.insight_service.record_experiment_feedback(user_id, current.id, "did_not_help")
        if intent.intent_type == "explain_insight":
            return self.insight_service.explain_insight(user_id, current.id)
        return None

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
        if lowered in {
            "yes",
            "yes remember that",
            "yes save that",
            "save it",
            "remember it",
            "да",
            "да запомни",
            "да сохрани",
            "сохрани",
            "запомни",
        }:
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
            "нет",
            "не сохраняй",
            "нет не сохраняй",
            "не надо",
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
