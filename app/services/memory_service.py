import logging
import re
from typing import Iterable

from pydantic import ValidationError

from app.models.extractor import MemoryExtractionResult, MemoryUpdateProposal
from app.models.memory import (
    MemoryCreateRequest,
    MemoryFeedback,
    MemoryRecord,
    MemoryType,
    MemoryUpdateRequest,
)
from app.models.safety import SafetyClassification
from app.repositories.memory_repository import MemoryRepository
from app.services.personalization_service import PersonalizationService

logger = logging.getLogger(__name__)

INITIAL_MEMORIES: tuple[tuple[MemoryType, str, float, str], ...] = (
    ("fixed_goal", "User wants to wake up every day at 09:00.", 1.0, "seed"),
    ("preference", "User does not want daily sleep reports.", 1.0, "seed"),
    ("preference", "User wants free-form chat advice.", 1.0, "seed"),
    (
        "preference",
        "User wants science-based, practical, concise, non-judgmental advice.",
        1.0,
        "seed",
    ),
    ("pattern", "User often struggles with snoozing alarms.", 0.95, "seed"),
    (
        "pattern",
        "User sometimes wakes earlier than planned at a repeated time.",
        0.8,
        "seed",
    ),
)


class MemoryService:
    def __init__(self, repository: MemoryRepository, user_id: str) -> None:
        self.repository = repository
        self.user_id = user_id
        self.personalization = PersonalizationService(repository, user_id)

    def ensure_seed_memories(self) -> None:
        for memory_type, content, confidence, source in INITIAL_MEMORIES:
            if self.repository.find_similar_memory(self.user_id, memory_type, content):
                continue
            self.repository.create_memory(
                user_id=self.user_id,
                memory_type=memory_type,
                content=content,
                confidence=confidence,
                source=source,
            )

    def list_memories(self, include_archived: bool = False) -> list[MemoryRecord]:
        return self.repository.list_memories(self.user_id, include_archived=include_archived)

    def get_memory(self, memory_id: str) -> MemoryRecord:
        return self.repository.get_memory(memory_id, self.user_id)

    def get_relevant_memories(self, message: str) -> list[MemoryRecord]:
        memories = self.repository.get_relevant_memories(self.user_id, message)
        return self.personalization.rank_memories(memories, message)

    def mark_memories_used(self, memories: Iterable[MemoryRecord]) -> None:
        self.repository.touch_memories(self.user_id, [memory.id for memory in memories])

    def create_memory(self, request: MemoryCreateRequest) -> MemoryRecord:
        existing = self.repository.find_similar_memory(
            self.user_id, request.type, request.content
        )
        if existing:
            return existing
        return self.repository.create_memory(
            user_id=self.user_id,
            memory_type=request.type,
            content=request.content,
            confidence=request.confidence,
            source=request.source,
            evidence_count=request.evidence_count,
            positive_count=request.positive_count,
            negative_count=request.negative_count,
            last_confirmed_at=request.last_confirmed_at,
            related_memory_id=request.related_memory_id,
            relation_type=request.relation_type,
        )

    def update_memory(self, memory_id: str, request: MemoryUpdateRequest) -> MemoryRecord:
        return self.repository.update_memory(
            memory_id,
            self.user_id,
            content=request.content,
            confidence=request.confidence,
            source=request.source,
            evidence_count=request.evidence_count,
            positive_count=request.positive_count,
            negative_count=request.negative_count,
            last_confirmed_at=request.last_confirmed_at,
            related_memory_id=request.related_memory_id,
            relation_type=request.relation_type,
            is_archived=request.is_archived,
        )

    def archive_memory(self, memory_id: str) -> MemoryRecord:
        return self.repository.archive_memory(memory_id, self.user_id)

    def archive_by_text(self, text: str) -> MemoryRecord | None:
        memories = self.list_memories(include_archived=False)
        query_tokens = set(re.findall(r"[a-z0-9:]+", text.lower()))
        best: tuple[int, MemoryRecord] | None = None

        for memory in memories:
            memory_tokens = set(re.findall(r"[a-z0-9:]+", memory.content.lower()))
            score = len(query_tokens & memory_tokens)
            if score == 0:
                continue
            if best is None or score > best[0]:
                best = (score, memory)

        if best is None:
            return None
        return self.archive_memory(best[1].id)

    def update_goal(self, wake_time: str) -> MemoryRecord:
        goal_content = f"User wants to wake up every day at {wake_time}."
        current_goals = [
            memory
            for memory in self.list_memories(include_archived=False)
            if memory.type == "fixed_goal"
        ]
        if current_goals:
            return self.repository.update_memory(
                current_goals[0].id,
                self.user_id,
                content=goal_content,
                confidence=1.0,
                source="user_request",
            )
        return self.repository.create_memory(
            user_id=self.user_id,
            memory_type="fixed_goal",
            content=goal_content,
            confidence=1.0,
            source="user_request",
        )

    def render_memory_summary(self) -> str:
        memories = self.list_memories(include_archived=False)
        if not memories:
            return "I do not have any saved memories about you yet."

        grouped: dict[str, list[MemoryRecord]] = {}
        for memory in memories:
            grouped.setdefault(memory.type, []).append(memory)

        lines = ["Here is what I currently remember about you:"]
        for memory_type in [
            "fixed_goal",
            "preference",
            "pattern",
            "hypothesis",
            "worked_before",
            "did_not_work",
        ]:
            items = grouped.get(memory_type)
            if not items:
                continue
            lines.append(f"{memory_type}:")
            lines.extend(
                f"- {item.content} (confidence: {item.confidence:.2f}, evidence: {item.evidence_count})"
                for item in items
            )
        return "\n".join(lines)

    def get_memories_by_ids(self, memory_ids: list[str]) -> list[MemoryRecord]:
        if not memory_ids:
            return []
        memory_map = {
            memory.id: memory
            for memory in self.list_memories(include_archived=True)
        }
        return [memory_map[memory_id] for memory_id in memory_ids if memory_id in memory_map]

    def validate_extraction_result(
        self, extraction: MemoryExtractionResult
    ) -> MemoryExtractionResult:
        if extraction.skip_memory:
            return MemoryExtractionResult(memory_updates=[], skip_memory=True, ignored=extraction.ignored)

        valid_updates: list[MemoryUpdateProposal] = []
        ignored = list(extraction.ignored)
        current_ids = {memory.id for memory in self.list_memories(include_archived=True)}

        for proposal in extraction.memory_updates:
            if proposal.sensitivity == "crisis":
                ignored.append(
                    {
                        "content": proposal.content or "",
                        "reason": "Crisis content should not be stored as ordinary memory.",
                    }
                )
                continue

            if proposal.action == "none":
                valid_updates.append(proposal)
                continue

            if proposal.type is None or proposal.content is None or proposal.confidence is None:
                ignored.append(
                    {"content": proposal.content or "", "reason": "Incomplete memory proposal."}
                )
                continue

            if self._looks_temporary(proposal.content):
                ignored.append(
                    {
                        "content": proposal.content,
                        "reason": "Temporary event, not durable memory.",
                    }
                )
                continue

            if self._looks_diagnostic(proposal.content):
                ignored.append(
                    {
                        "content": proposal.content,
                        "reason": "Diagnosis-like medical memory should not be stored.",
                    }
                )
                continue

            if self._looks_too_sensitive(proposal.content):
                ignored.append(
                    {
                        "content": proposal.content,
                        "reason": "Sensitive crisis or medical details should not be stored as ordinary memory.",
                    }
                )
                continue

            if proposal.action in {"update", "archive"} and proposal.target_memory_id not in current_ids:
                ignored.append(
                    {
                        "content": proposal.content,
                        "reason": "Target memory id does not exist.",
                    }
                )
                continue

            valid_updates.append(proposal)

        try:
            return MemoryExtractionResult(
                memory_updates=valid_updates,
                skip_memory=extraction.skip_memory,
                ignored=ignored,
            )
        except ValidationError as exc:
            logger.warning("Memory extraction validation failed: %s", exc)
            return MemoryExtractionResult(memory_updates=[], ignored=[])

    def apply_memory_updates(self, extraction: MemoryExtractionResult) -> list[MemoryRecord]:
        existing_memories = self.list_memories(include_archived=True)
        proposals = self.personalization.merge_duplicate_memories(
            extraction.memory_updates,
            existing_memories,
        )
        proposals = self.personalization.detect_contradictions(existing_memories, proposals)
        applied: list[MemoryRecord] = []
        for proposal in proposals:
            if proposal.action == "none":
                continue

            assert proposal.type is not None
            assert proposal.content is not None
            assert proposal.confidence is not None

            if proposal.action == "create":
                memory = self.create_memory(
                    MemoryCreateRequest(
                        type=proposal.type,
                        content=proposal.content,
                        confidence=proposal.confidence,
                        source="memory_extractor",
                        related_memory_id=proposal.related_memory_id,
                        relation_type=proposal.relation_type,
                    )
                )
                applied.append(memory)
                continue

            if proposal.action == "update" and proposal.target_memory_id:
                memory = self.update_memory(
                    proposal.target_memory_id,
                    MemoryUpdateRequest(
                        content=proposal.content,
                        confidence=proposal.confidence,
                        source="memory_extractor",
                        related_memory_id=proposal.related_memory_id,
                        relation_type=proposal.relation_type,
                    ),
                )
                applied.append(memory)
                continue

            if proposal.action == "archive" and proposal.target_memory_id:
                memory = self.archive_memory(proposal.target_memory_id)
                applied.append(memory)

        return applied

    def get_personalization_context(self, message: str) -> str:
        memories = self.repository.list_memories(self.user_id, include_archived=False)
        context = self.personalization.get_personalization_context(message, memories)
        return self.personalization.build_compact_context_text(context)

    def apply_feedback(self, memory_id: str, feedback: MemoryFeedback) -> MemoryRecord:
        memory = self.repository.get_memory(memory_id, self.user_id)
        return self.personalization.update_memory_confidence(memory, feedback)

    def record_intervention_feedback(self, intervention: str, result: str) -> MemoryRecord:
        return self.personalization.record_intervention_result(intervention, result)

    def restrict_extraction_for_safety(
        self,
        extraction: MemoryExtractionResult,
        safety: SafetyClassification,
    ) -> MemoryExtractionResult:
        if safety.category == "D":
            return MemoryExtractionResult(
                memory_updates=[],
                skip_memory=extraction.skip_memory,
                ignored=extraction.ignored,
            )

        if safety.category != "C":
            return extraction

        allowed_updates: list[MemoryUpdateProposal] = []
        ignored = list(extraction.ignored)
        for proposal in extraction.memory_updates:
            if proposal.action == "none":
                allowed_updates.append(proposal)
                continue
            if proposal.content is None:
                continue
            if self._looks_diagnostic(proposal.content) or self._looks_too_sensitive(
                proposal.content
            ):
                ignored.append(
                    {
                        "content": proposal.content,
                        "reason": "Restricted due to medical red flag context.",
                    }
                )
                continue
            if (
                "breathing-related sleep concerns" in proposal.content.lower()
                or "avoid treating this as a routine sleep hygiene issue"
                in proposal.content.lower()
            ):
                allowed_updates.append(proposal)
        return MemoryExtractionResult(
            memory_updates=allowed_updates,
            skip_memory=extraction.skip_memory,
            ignored=ignored,
        )

    @staticmethod
    def _looks_temporary(content: str) -> bool:
        lowered = content.lower()
        return any(token in lowered for token in ("yesterday", "last night", "today", "tonight"))

    @staticmethod
    def _looks_diagnostic(content: str) -> bool:
        lowered = content.lower()
        blocked_terms = (
            "has insomnia",
            "has sleep apnea",
            "diagnosed",
            "depression",
            "anxiety disorder",
        )
        return any(term in lowered for term in blocked_terms)

    @staticmethod
    def _looks_too_sensitive(content: str) -> bool:
        lowered = content.lower()
        blocked_terms = (
            "hurt myself",
            "kill myself",
            "want to die",
            "suicide",
            "suicidal",
            "hopeless",
            "stop breathing",
            "stops breathing",
            "breathing pauses",
            "gasping",
            "wake up choking",
            "dangerously sleepy while driving",
        )
        return any(term in lowered for term in blocked_terms)
