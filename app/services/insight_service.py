from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.chat import HistoryMessage
from app.models.insight import (
    InsightCandidate,
    InsightCreateRequest,
    InsightPreferenceRecord,
    InsightPreferenceUpdateRequest,
    InsightRecord,
    InsightUpdateRequest,
)
from app.models.memory import MemoryCreateRequest
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.memory_repository import tokenize, utc_now_iso
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService
from app.services.openai_client import OpenAIResponseService


@dataclass
class InsightIntent:
    intent_type: str


class InsightService:
    def __init__(
        self,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        openai_service: OpenAIResponseService,
        advice_trace_repository: AdviceTraceRepository,
        insight_repository: InsightRepository,
    ) -> None:
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.openai_service = openai_service
        self.advice_trace_repository = advice_trace_repository
        self.insight_repository = insight_repository

    def detect_intent(self, message: str) -> InsightIntent:
        lowered = message.strip().lower()
        if lowered in {
            "what patterns do you notice?",
            "what patterns do you notice",
            "do you see any sleep patterns?",
            "do you see any sleep patterns",
            "what have you learned about my sleep?",
            "what have you learned about my sleep",
            "why am i struggling to wake at 9?",
            "why am i struggling to wake at 9",
            "what should i experiment with this week?",
            "what should i experiment with this week",
        }:
            return InsightIntent("manual_insights")
        if lowered in {"don't give me proactive insights.", "don't give me proactive insights", "dont give me proactive insights"}:
            return InsightIntent("disable_proactive_insights")
        if lowered in {"turn insights back on.", "turn insights back on", "enable proactive insights"}:
            return InsightIntent("enable_proactive_insights")
        if lowered in {"dismiss this insight.", "dismiss this insight"}:
            return InsightIntent("dismiss_insight")
        if lowered in {"forget this insight.", "forget this insight", "archive this insight"}:
            return InsightIntent("archive_insight")
        if lowered in {"save this as a pattern.", "save this as a pattern"}:
            return InsightIntent("save_insight_as_pattern")
        if lowered in {"this insight is wrong.", "this insight is wrong", "that insight is wrong"}:
            return InsightIntent("reject_insight")
        if lowered in {"that experiment helped.", "that experiment helped", "that helped."}:
            return InsightIntent("experiment_helped")
        if lowered in {
            "that experiment did not help.",
            "that experiment did not help",
            "that experiment didn't help",
            "that did not help.",
        }:
            return InsightIntent("experiment_failed")
        if lowered in {"why do you think that?", "why do you think that", "what evidence do you have?", "what evidence do you have", "how confident are you?", "how confident are you"}:
            return InsightIntent("explain_insight")
        return InsightIntent("normal_chat")

    def get_preferences(self) -> InsightPreferenceRecord:
        return self.insight_repository.get_preferences(self.memory_service.user_id)

    def update_preferences(
        self,
        request: InsightPreferenceUpdateRequest,
    ) -> InsightPreferenceRecord:
        return self.insight_repository.update_preferences(self.memory_service.user_id, request)

    def list_insights(self, include_archived: bool = False) -> list[InsightRecord]:
        return self.insight_repository.list_insights(
            self.memory_service.user_id,
            include_archived=include_archived,
        )

    def get_latest_actionable_insight(self) -> InsightRecord | None:
        return self.insight_repository.get_latest_shown_active_insight(self.memory_service.user_id)

    def get_manual_insights(
        self,
        user_id: str,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None,
    ) -> str:
        del user_id, history, session_id
        insights = self.generate_insight_candidates(
            self.memory_service.user_id,
            message,
            [],
            None,
            max_candidates=2,
        )
        if not insights:
            return (
                "I do not see a solid pattern yet. The strongest guess is still too weak to treat as more than a hypothesis, "
                "so for now I would keep the focus on a simple 09:00 wake-up experiment rather than overreading the data."
            )
        for insight in insights:
            self.mark_insight_shown(self.memory_service.user_id, insight.id)
        return self._format_manual_insight_response(insights[:2])

    def should_generate_proactive_insight(
        self,
        user_id: str,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None,
        safety_category: str,
    ) -> bool:
        del message, history, session_id
        if safety_category in {"C", "D"}:
            return False
        preferences = self.insight_repository.get_preferences(user_id)
        if not preferences.proactive_insights_enabled:
            return False
        if not self.insight_repository.is_older_than_week(preferences.last_proactive_insight_at):
            return False
        traces = self.advice_trace_repository.list_recent_traces(
            user_id,
            include_private=False,
            since_iso=preferences.last_proactive_insight_at,
            limit=20,
        )
        if len(traces) >= preferences.insight_min_evidence_threshold:
            return True
        recent_memories = self.memory_service.list_memories(include_archived=False)
        fresh_feedback = [
            memory
            for memory in recent_memories
            if memory.type in {"worked_before", "did_not_work"}
            and (
                preferences.last_proactive_insight_at is None
                or memory.updated_at >= preferences.last_proactive_insight_at
            )
        ]
        if len(fresh_feedback) >= 2:
            return True
        repeated_issue = self._detect_repeated_issue(traces)
        return repeated_issue is not None and len(traces) >= 3

    def generate_insight_candidates(
        self,
        user_id: str,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None,
        *,
        max_candidates: int = 1,
    ) -> list[InsightRecord]:
        del session_id
        memories = self.memory_service.list_memories(include_archived=False)
        preferences = self.insight_repository.get_preferences(user_id)
        traces = self.advice_trace_repository.list_recent_traces(
            user_id,
            include_private=False,
            since_iso=preferences.last_proactive_insight_at,
            limit=20,
        )
        if not traces and len(memories) < 2:
            return []

        recent_text = " ".join(trace.user_message for trace in traces[:6])
        knowledge_cards = self.knowledge_service.get_relevant_knowledge_cards(
            message or recent_text or "sleep patterns",
            memories,
        )
        generation = self.openai_service.generate_insight_candidates(
            user_message=message,
            history=history,
            recent_traces=traces,
            memories=memories,
            relevant_knowledge_cards=knowledge_cards,
            last_insight_at=preferences.last_proactive_insight_at,
            max_candidates=max_candidates,
        )
        if not generation.should_create_insight:
            return []

        created: list[InsightRecord] = []
        for candidate in generation.insights[:max_candidates]:
            if not self._is_candidate_valid(candidate, traces):
                continue
            if self.insight_repository.find_duplicate_insight(
                user_id,
                candidate.title,
                candidate.summary,
            ):
                continue
            insight = self.create_insight(
                user_id,
                candidate,
                traces=traces,
                memories=memories,
                knowledge_card_ids=[card.id for card in knowledge_cards[:3]],
            )
            created.append(insight)
        return created

    def create_insight(
        self,
        user_id: str,
        insight_candidate: InsightCandidate,
        *,
        traces: list,
        memories: list,
        knowledge_card_ids: list[str],
    ) -> InsightRecord:
        related_memory_ids = self._match_memory_ids(insight_candidate, memories)
        related_message_ids = [trace.id for trace in traces[:5]]
        request = InsightCreateRequest(
            title=insight_candidate.title,
            summary=insight_candidate.summary,
            evidence=insight_candidate.evidence,
            confidence=insight_candidate.confidence,
            suggested_experiment=insight_candidate.suggested_experiment,
            related_memory_ids=related_memory_ids,
            related_message_ids=related_message_ids,
            related_knowledge_card_ids=knowledge_card_ids,
        )
        return self.insight_repository.create_insight(user_id, request)

    def dismiss_insight(self, user_id: str, insight_id: str) -> InsightRecord | None:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return None
        return self.insight_repository.update_insight(
            insight_id,
            user_id,
            InsightUpdateRequest(status="dismissed"),
        )

    def archive_insight(self, user_id: str, insight_id: str) -> InsightRecord | None:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return None
        return self.insight_repository.update_insight(
            insight_id,
            user_id,
            InsightUpdateRequest(status="archived"),
        )

    def explain_insight(self, user_id: str, insight_id: str) -> str:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return "I do not have a recent insight to explain right now."
        confidence_text = {
            "high": "I am fairly confident because you have mentioned the same pattern repeatedly or confirmed it directly.",
            "medium": "I would call this a working pattern rather than a certainty.",
            "low": "I would treat this as a hypothesis for now, not a fact.",
        }[insight.confidence]
        evidence_text = " ".join(insight.evidence[:3])
        return f"I think that because {evidence_text} {confidence_text}"

    def record_experiment_feedback(
        self,
        user_id: str,
        insight_id: str,
        feedback: str,
    ) -> str:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return "I do not have a recent experiment to link that feedback to."
        result = "helped" if feedback == "helped" else "did_not_help"
        memory = self.memory_service.record_intervention_feedback(
            insight.suggested_experiment,
            result,
        )
        if feedback == "did_not_help":
            self.archive_insight(user_id, insight_id)
            return f"Thanks. I will treat that experiment as unhelpful for now: {memory.content}"
        self.mark_insight_shown(user_id, insight_id, proactive=True)
        return f"Good to know. I will remember that this helped: {memory.content}"

    def mark_insight_shown(
        self,
        user_id: str,
        insight_id: str,
        *,
        proactive: bool = False,
    ) -> InsightRecord | None:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return None
        updated = self.insight_repository.update_insight(
            insight_id,
            user_id,
            InsightUpdateRequest(last_shown_at=utc_now_iso()),
        )
        if proactive:
            self.insight_repository.update_preferences(
                user_id,
                InsightPreferenceUpdateRequest(last_proactive_insight_at=utc_now_iso()),
            )
        return updated

    def handle_rejected_insight(self, user_id: str, insight_id: str) -> str:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return "I do not have a recent insight to correct."
        self.dismiss_insight(user_id, insight_id)
        for memory_id in insight.related_memory_ids:
            self.memory_service.apply_feedback(memory_id, "wrong")
        return "Thanks for correcting me. I will treat that insight as unreliable and stop surfacing it."

    def save_insight_as_pattern(self, user_id: str, insight_id: str) -> str:
        insight = self.insight_repository.get_insight(insight_id, user_id)
        if insight is None:
            return "I do not have a recent insight to save as a pattern."
        memory = self.memory_service.create_memory(
            MemoryCreateRequest(
                type="pattern",
                content=insight.summary,
                confidence=0.9 if insight.confidence == "high" else 0.7,
                source="insight_feedback",
                positive_count=1,
            )
        )
        return f"Okay — I saved that as a pattern: {memory.content}"

    def maybe_get_proactive_insight_reply(
        self,
        user_id: str,
        message: str,
        history: list[HistoryMessage],
        session_id: str | None,
        safety_category: str,
    ) -> str | None:
        if not self.should_generate_proactive_insight(
            user_id,
            message,
            history,
            session_id,
            safety_category,
        ):
            return None
        insights = self.generate_insight_candidates(
            user_id,
            message,
            history,
            session_id,
            max_candidates=1,
        )
        if not insights:
            return None
        insight = insights[0]
        self.mark_insight_shown(user_id, insight.id, proactive=True)
        prefix = "One useful pattern I am starting to notice: "
        if insight.confidence == "low":
            prefix = "One possible pattern I am starting to notice: "
        return f"{prefix}{insight.summary} Small experiment: {insight.suggested_experiment}"

    def _is_candidate_valid(self, candidate: InsightCandidate, traces: list) -> bool:
        if candidate.confidence == "low" and len(candidate.evidence) < 2:
            return False
        if len(candidate.evidence) < 1:
            return False
        lowered = " ".join([candidate.title, candidate.summary, candidate.suggested_experiment]).lower()
        blocked_terms = (
            "melatonin",
            "supplement",
            "medication",
            "diagnosis",
            "sleep apnea",
            "suicide",
            "self-harm",
            "daily report",
            "track every day",
        )
        if any(term in lowered for term in blocked_terms):
            return False
        if not self._looks_small_experiment(candidate.suggested_experiment):
            return False
        return True

    @staticmethod
    def _looks_small_experiment(text: str) -> bool:
        lowered = text.lower()
        if "for the next" in lowered or "for three" in lowered or "for a few days" in lowered:
            return True
        return any(token in lowered for token in ("try ", "keep ", "avoid ", "use ", "move "))

    @staticmethod
    def _detect_repeated_issue(traces: list) -> str | None:
        issue_terms = ("snooze", "alarm", "groggy", "wake", "nap", "caffeine", "bedtime")
        counts: dict[str, int] = {term: 0 for term in issue_terms}
        for trace in traces:
            lowered = trace.user_message.lower()
            for term in issue_terms:
                if term in lowered:
                    counts[term] += 1
        repeated = max(counts.items(), key=lambda item: item[1])
        return repeated[0] if repeated[1] >= 2 else None

    @staticmethod
    def _match_memory_ids(candidate: InsightCandidate, memories: list) -> list[str]:
        candidate_tokens = tokenize(
            " ".join(
                [candidate.title, candidate.summary, candidate.suggested_experiment]
            )
        )
        matched: list[str] = []
        for memory in memories:
            overlap = len(candidate_tokens & tokenize(memory.content))
            if overlap >= 2:
                matched.append(memory.id)
        return matched[:5]

    @staticmethod
    def _format_manual_insight_response(insights: list[InsightRecord]) -> str:
        lines = []
        solid: list[InsightRecord] = []
        tentative: list[InsightRecord] = []
        for insight in insights:
            if insight.confidence == "low":
                tentative.append(insight)
            else:
                solid.append(insight)
        if solid:
            lines.append("I see a few patterns. The strongest one is:")
            for index, insight in enumerate(solid, start=1):
                lines.append(f"{index}. {insight.summary}")
        if tentative:
            lines.append("Possible hypothesis:")
            for insight in tentative:
                lines.append(f"- {insight.summary}")
        best = insights[0]
        lines.append("")
        lines.append("Best experiment for this week:")
        lines.append(best.suggested_experiment)
        return "\n".join(lines).strip()

    @staticmethod
    def maybe_extract_wake_time_variant(message: str) -> str:
        match = re.search(r"wake at\s+(9|09:00|9:00)", message.lower())
        return match.group(0) if match else ""
