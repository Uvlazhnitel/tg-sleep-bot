import json
import re
from dataclasses import dataclass

from app.models.extractor import MemoryExtractionResult, MemoryUpdateProposal
from app.models.memory import MemoryCreateRequest, MemoryRecord, MemoryUpdateRequest
from app.models.memory_control import (
    DEFAULT_SESSION_ID,
    AdviceTraceRecord,
    MemorySessionStateRecord,
    PendingMemoryConfirmationRecord,
)
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.pending_memory_confirmation_repository import (
    PendingMemoryConfirmationRepository,
)
from app.repositories.memory_repository import tokenize
from app.repositories.session_state_repository import SessionStateRepository
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService


@dataclass
class MemoryIntent:
    intent_type: str
    payload: str | None = None


@dataclass
class MemoryMatchResult:
    exact: MemoryRecord | None
    strong_matches: list[MemoryRecord]


class MemoryTransparencyService:
    def __init__(
        self,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        advice_trace_repository: AdviceTraceRepository,
        session_state_repository: SessionStateRepository,
        pending_confirmation_repository: PendingMemoryConfirmationRepository,
    ) -> None:
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.advice_trace_repository = advice_trace_repository
        self.session_state_repository = session_state_repository
        self.pending_confirmation_repository = pending_confirmation_repository

    @staticmethod
    def normalize_session_id(session_id: str | None) -> str:
        return session_id or DEFAULT_SESSION_ID

    def detect_intent(self, message: str) -> MemoryIntent:
        lowered = message.strip().lower()

        if lowered in {
            "what do you remember about me?",
            "show my memory.",
            "show my memory",
            "what sleep context do you have about me?",
            "what are you using to personalize advice?",
            "/memory",
        }:
            return MemoryIntent("show_memory")

        if lowered in {
            "don't remember this",
            "dont remember this",
            "don't save anything from this conversation",
            "dont save anything from this conversation",
        }:
            return MemoryIntent("disable_memory_for_turn")

        if lowered in {"private mode", "/private", "memory off", "/memory_off"}:
            return MemoryIntent("disable_memory_for_session")

        if lowered in {"memory on", "/memory_on", "enable memory"}:
            return MemoryIntent("enable_memory_for_session")

        if any(
            phrase in lowered
            for phrase in (
                "why did you recommend",
                "why do you recommend",
                "why did you say",
                "what are you basing this on",
                "is that because of something you remember about me",
            )
        ):
            return MemoryIntent("explain_advice")

        delete_match = re.match(
            r"^(forget|delete|remove)(?: everything about| that| this| the)?\s+(?P<payload>.+)$",
            lowered,
        )
        if delete_match:
            return MemoryIntent("delete_memory", delete_match.group("payload"))

        if lowered.startswith("change my wake-up goal to ") or lowered.startswith(
            "change my wake up goal to "
        ):
            return MemoryIntent("update_memory", message)

        if (
            lowered.startswith("actually")
            or "doesn't affect my sleep" in lowered
            or "does not affect my sleep" in lowered
            or "did not actually help" in lowered
            or "want more detailed explanations" in lowered
            or "don't snooze that often anymore" in lowered
            or "dont snooze that often anymore" in lowered
        ):
            return MemoryIntent("update_memory", message)

        return MemoryIntent("normal_chat")

    def summarize_memories_for_user(self) -> str:
        memories = self.memory_service.list_memories(include_archived=False)
        return self.format_memory_summary_for_user(memories)

    def format_memory_summary_for_user(self, memories: list[MemoryRecord]) -> str:
        grouped: dict[str, list[str]] = {
            "Goal": [],
            "Preferences": [],
            "Patterns": [],
            "Hypotheses": [],
            "What worked before": [],
            "What did not work": [],
            "Safety-relevant notes": [],
        }
        for memory in memories:
            if self._is_safety_note(memory):
                grouped["Safety-relevant notes"].append(f"- {memory.content}")
            elif memory.type == "fixed_goal":
                grouped["Goal"].append(f"- {memory.content}")
            elif memory.type == "preference":
                grouped["Preferences"].append(f"- {memory.content}")
            elif memory.type == "pattern":
                grouped["Patterns"].append(f"- {memory.content}")
            elif memory.type == "hypothesis":
                grouped["Hypotheses"].append(f"- {memory.content} (still uncertain)")
            elif memory.type == "worked_before":
                grouped["What worked before"].append(f"- {memory.content}")
            elif memory.type == "did_not_work":
                grouped["What did not work"].append(f"- {memory.content}")

        lines = ["I currently remember:"]
        for heading in [
            "Goal",
            "Preferences",
            "Patterns",
            "Hypotheses",
            "What worked before",
            "What did not work",
            "Safety-relevant notes",
        ]:
            items = grouped[heading]
            if not items:
                continue
            lines.append(f"{heading}:")
            lines.extend(items)
            lines.append("")
        lines.append('You can tell me "forget X" or "update X" anytime.')
        return "\n".join(lines).strip()

    def find_memories_for_deletion(self, user_text: str) -> MemoryMatchResult:
        memories = self.memory_service.list_memories(include_archived=False)
        return self._find_matching_memories(user_text, memories)

    def find_memories_for_update(self, user_text: str) -> MemoryMatchResult:
        memories = self.memory_service.list_memories(include_archived=False)
        return self._find_matching_memories(user_text, memories)

    def archive_memory(self, memory_id: str) -> MemoryRecord:
        return self.memory_service.archive_memory(memory_id)

    def update_memory(self, memory_id: str, patch: MemoryUpdateRequest) -> MemoryRecord:
        return self.memory_service.update_memory(memory_id, patch)

    def get_session_state(self, session_id: str | None) -> MemorySessionStateRecord | None:
        return self.session_state_repository.get_state(
            self.memory_service.user_id,
            self.normalize_session_id(session_id),
        )

    def is_memory_enabled_for_session(self, session_id: str | None) -> bool:
        state = self.get_session_state(session_id)
        return True if state is None else state.memory_enabled

    def set_memory_disabled_for_session(
        self,
        session_id: str | None,
        enabled: bool,
    ) -> MemorySessionStateRecord:
        return self.session_state_repository.set_memory_enabled(
            self.memory_service.user_id,
            self.normalize_session_id(session_id),
            enabled,
        )

    def store_advice_trace(
        self,
        session_id: str | None,
        user_message: str,
        assistant_reply: str,
        source_memory_ids: list[str],
        knowledge_card_ids: list[str],
        safety_category: str,
    ) -> AdviceTraceRecord:
        return self.advice_trace_repository.create_trace(
            user_id=self.memory_service.user_id,
            session_id=self.normalize_session_id(session_id),
            user_message=user_message,
            assistant_reply=assistant_reply,
            source_memory_ids=source_memory_ids,
            knowledge_card_ids=knowledge_card_ids,
            safety_category=safety_category,
        )

    def explain_last_advice(self, session_id: str | None) -> str:
        trace = self.advice_trace_repository.get_latest_trace(
            self.memory_service.user_id,
            self.normalize_session_id(session_id),
        )
        if trace is None:
            return "I do not have enough recent context to explain that specific advice yet."

        memory_items = self.memory_service.get_memories_by_ids(trace.source_memory_ids)
        cards = [
            self.knowledge_service.get_knowledge_card_by_id(card_id)
            for card_id in trace.knowledge_card_ids
        ]
        cards = [card for card in cards if card is not None]

        parts = [
            "I based that on your goal of protecting a stable wake-up time around 09:00."
        ]
        if memory_items:
            memory_text = memory_items[0].content
            parts.append(f"I also used your saved context that {memory_text.lower()}")
        else:
            parts.append("I was not relying on a specific personal memory for that part.")
        if cards:
            parts.append(
                f"I was also using general sleep guidance about {cards[0].title.lower()}."
            )
        if trace.safety_category in {"C", "D"}:
            parts.append(
                "Safety concerns also affected the advice, so I kept the guidance more conservative."
            )
        return " ".join(parts)

    def get_pending_confirmation(
        self,
        session_id: str | None,
    ) -> PendingMemoryConfirmationRecord | None:
        return self.pending_confirmation_repository.get_pending_confirmation(
            self.memory_service.user_id,
            self.normalize_session_id(session_id),
        )

    def create_pending_confirmation(
        self,
        session_id: str | None,
        extraction: MemoryExtractionResult,
    ) -> PendingMemoryConfirmationRecord:
        prompt_text = self._build_sensitive_confirmation_prompt(extraction.memory_updates)
        return self.pending_confirmation_repository.create_pending_confirmation(
            user_id=self.memory_service.user_id,
            session_id=self.normalize_session_id(session_id),
            memory_updates_json=extraction.model_dump_json(),
            prompt_text=prompt_text,
        )

    def resolve_pending_confirmation(
        self,
        session_id: str | None,
        accept: bool,
    ) -> str:
        session_key = self.normalize_session_id(session_id)
        pending = self.get_pending_confirmation(session_key)
        if pending is None:
            return "There is no pending memory request to resolve right now."

        self.pending_confirmation_repository.delete_pending_confirmation(
            self.memory_service.user_id,
            session_key,
        )
        if not accept:
            return "Okay — I will not save that to memory."

        extraction = MemoryExtractionResult.model_validate_json(pending.memory_updates_json)
        validated = self.memory_service.validate_extraction_result(extraction)
        self.memory_service.apply_memory_updates(validated)
        return "Okay — I saved that for future sleep advice."

    def should_ask_before_saving(self, proposal: MemoryUpdateProposal) -> bool:
        return proposal.should_ask_user_before_saving or proposal.sensitivity == "sensitive"

    def split_sensitive_updates(
        self,
        extraction: MemoryExtractionResult,
    ) -> tuple[MemoryExtractionResult, MemoryExtractionResult | None]:
        normal_updates: list[MemoryUpdateProposal] = []
        sensitive_updates: list[MemoryUpdateProposal] = []
        for proposal in extraction.memory_updates:
            if proposal.sensitivity == "crisis":
                continue
            if self.should_ask_before_saving(proposal):
                sensitive_updates.append(proposal)
            else:
                normal_updates.append(proposal)

        normal_result = MemoryExtractionResult(
            memory_updates=normal_updates,
            skip_memory=extraction.skip_memory,
            ignored=extraction.ignored,
        )
        sensitive_result = (
            MemoryExtractionResult(
                memory_updates=sensitive_updates,
                skip_memory=False,
                ignored=[],
            )
            if sensitive_updates
            else None
        )
        return normal_result, sensitive_result

    def handle_update_request(self, message: str) -> str | None:
        lowered = message.lower()

        goal_match = re.search(r"change my wake[ -]?up goal to (?P<time>\d{1,2}:\d{2})", lowered)
        if goal_match:
            memory = self.memory_service.update_goal(goal_match.group("time"))
            return f"Okay — I updated your wake-up goal to {goal_match.group('time')}."

        if (
            "coffee doesn't affect my sleep" in lowered
            or "coffee does not affect my sleep" in lowered
            or "caffeine doesn't affect my sleep" in lowered
            or "caffeine does not affect my sleep" in lowered
        ):
            match = self.find_memories_for_update("coffee caffeine sleep")
            target = match.exact or (match.strong_matches[0] if match.strong_matches else None)
            if target is None:
                return "Okay — I will not treat caffeine as a likely cause unless you bring it up again."
            updated = self.memory_service.apply_feedback(target.id, "wrong")
            if updated.is_archived:
                return "Got it — I removed that caffeine-related hypothesis from memory."
            return "Got it — I downgraded that caffeine-related memory and will treat it more cautiously."

        if "morning light did not actually help" in lowered or "morning light didn't actually help" in lowered:
            match = self.find_memories_for_update("morning light")
            target = match.exact or (match.strong_matches[0] if match.strong_matches else None)
            if target is not None:
                self.memory_service.apply_feedback(target.id, "wrong")
            self.memory_service.record_intervention_feedback("Morning light.", "did_not_help")
            return "Got it — I will stop treating morning light as a likely helper for you."

        if "want more detailed explanations" in lowered:
            memory = self.memory_service.create_memory(
                MemoryCreateRequest(
                    type="preference",
                    content="User wants more detailed explanations when useful.",
                    confidence=0.95,
                    source="user_request",
                    positive_count=1,
                )
            )
            return f"Okay — I will remember that: {memory.content}"

        if "don't snooze that often anymore" in lowered or "dont snooze that often anymore" in lowered:
            match = self.find_memories_for_update("snooze alarms")
            target = match.exact or (match.strong_matches[0] if match.strong_matches else None)
            if target is None:
                return "Got it — I will treat snoozing as less central for you."
            self.memory_service.update_memory(
                target.id,
                MemoryUpdateRequest(
                    content="User does not snooze as often anymore.",
                    confidence=min(target.confidence, 0.7),
                    source="user_request",
                ),
            )
            return "Got it — I updated that snoozing pattern to reflect that it is less true now."

        return None

    def handle_delete_request(self, payload: str) -> str:
        match = self.find_memories_for_deletion(payload)
        if match.exact is not None:
            archived = self.archive_memory(match.exact.id)
            return f"Done — I removed that memory: {archived.content}"
        if len(match.strong_matches) == 1:
            archived = self.archive_memory(match.strong_matches[0].id)
            return f"Done — I removed that memory: {archived.content}"
        if len(match.strong_matches) > 1:
            lines = ["I found a few possible matches. Which one should I remove?"]
            for index, memory in enumerate(match.strong_matches[:3], start=1):
                lines.append(f"{index}. {memory.content}")
            return "\n".join(lines)
        return "I could not confidently find a matching memory to remove."

    def _find_matching_memories(
        self,
        user_text: str,
        memories: list[MemoryRecord],
    ) -> MemoryMatchResult:
        query_tokens = tokenize(user_text)
        if "caffeine" in query_tokens:
            query_tokens.add("coffee")
        if "coffee" in query_tokens:
            query_tokens.add("caffeine")
        if "alcohol" in query_tokens:
            query_tokens.update({"drink", "drinking"})
        exact: MemoryRecord | None = None
        scored: list[tuple[int, MemoryRecord]] = []
        lowered = user_text.lower().strip()
        for memory in memories:
            memory_lowered = memory.content.lower()
            if lowered and lowered in memory_lowered:
                exact = memory
                break
            overlap = len(query_tokens & tokenize(memory.content))
            if overlap > 0:
                scored.append((overlap, memory))

        scored.sort(key=lambda item: (item[0], item[1].confidence), reverse=True)
        if exact is not None:
            return MemoryMatchResult(exact=exact, strong_matches=[exact])

        if not scored:
            return MemoryMatchResult(exact=None, strong_matches=[])

        top_score = scored[0][0]
        strong_matches = [memory for score, memory in scored if score >= max(1, top_score - 1)]
        return MemoryMatchResult(exact=None, strong_matches=strong_matches[:3])

    @staticmethod
    def _is_safety_note(memory: MemoryRecord) -> bool:
        lowered = memory.content.lower()
        return any(
            phrase in lowered
            for phrase in (
                "breathing-related sleep concerns",
                "routine sleep hygiene issue",
                "medication-related sleep concerns",
                "safety",
            )
        )

    @staticmethod
    def _build_sensitive_confirmation_prompt(
        proposals: list[MemoryUpdateProposal],
    ) -> str:
        lines = ["Do you want me to remember this for future sleep advice?"]
        for proposal in proposals:
            if proposal.content:
                lines.append(f"- {proposal.content}")
        return "\n".join(lines)
