import re
from dataclasses import dataclass

from app.models.extractor import MemoryExtractionResult, MemoryUpdateProposal
from app.models.memory import MemoryCreateRequest, MemoryFeedback, MemoryRecord, MemoryUpdateRequest
from app.repositories.memory_repository import MemoryRepository, tokenize, utc_now_iso


@dataclass
class PersonalizationContext:
    goal: list[MemoryRecord]
    preferences: list[MemoryRecord]
    relevant_context: list[MemoryRecord]
    worked_before: list[MemoryRecord]
    did_not_work: list[MemoryRecord]
    hypotheses: list[MemoryRecord]


class PersonalizationService:
    def __init__(self, repository: MemoryRepository, user_id: str) -> None:
        self.repository = repository
        self.user_id = user_id

    def rank_memories(self, memories: list[MemoryRecord], message: str) -> list[MemoryRecord]:
        message_tokens = tokenize(message)

        def score(memory: MemoryRecord) -> tuple[float, float, float, str]:
            memory_tokens = tokenize(memory.content)
            overlap = len(message_tokens & memory_tokens)
            base = float(overlap) * 3
            if memory.type == "fixed_goal":
                base += 2
            elif memory.type == "preference":
                base += 1.5
            elif memory.type in {"worked_before", "did_not_work"}:
                base += 3
            elif memory.type == "hypothesis":
                base -= max(0.0, 0.6 - memory.confidence)
            base += memory.confidence * 3
            base += min(memory.evidence_count, 5) * 0.4
            base += min(memory.positive_count, 5) * 0.25
            base -= min(memory.negative_count, 5) * 0.3
            recency = memory.last_confirmed_at or memory.last_used_at or memory.updated_at
            return (base, memory.confidence, float(memory.evidence_count), recency)

        return sorted(memories, key=score, reverse=True)

    def get_personalization_context(
        self,
        message: str,
        memories: list[MemoryRecord] | None = None,
    ) -> PersonalizationContext:
        source = memories if memories is not None else self.repository.list_memories(
            self.user_id,
            include_archived=False,
        )
        ranked = self.rank_memories(source, message)

        goal = [memory for memory in ranked if memory.type == "fixed_goal"][:1]
        preferences = [memory for memory in ranked if memory.type == "preference"][:3]
        worked_before = [memory for memory in ranked if memory.type == "worked_before"][:2]
        did_not_work = [memory for memory in ranked if memory.type == "did_not_work"][:2]
        hypotheses = [memory for memory in ranked if memory.type == "hypothesis"][:2]
        relevant_context = [
            memory
            for memory in ranked
            if memory.type == "pattern" and memory.confidence >= 0.65
        ][:3]

        return PersonalizationContext(
            goal=goal,
            preferences=preferences,
            relevant_context=relevant_context,
            worked_before=worked_before,
            did_not_work=did_not_work,
            hypotheses=hypotheses,
        )

    def update_memory_confidence(
        self,
        memory: MemoryRecord,
        signal: MemoryFeedback,
    ) -> MemoryRecord:
        confidence = memory.confidence
        evidence_count = memory.evidence_count
        positive_count = memory.positive_count
        negative_count = memory.negative_count
        last_confirmed_at = memory.last_confirmed_at
        is_archived = memory.is_archived
        now = utc_now_iso()

        if signal == "confirmed":
            confidence = min(1.0, confidence + 0.1)
            evidence_count += 1
            last_confirmed_at = now
        elif signal == "helped":
            confidence = min(1.0, confidence + 0.15)
            evidence_count += 1
            positive_count += 1
            last_confirmed_at = now
        elif signal == "did_not_help":
            confidence = max(0.0, confidence - 0.15)
            evidence_count += 1
            negative_count += 1
        elif signal == "wrong":
            confidence = max(0.0, confidence - 0.3)
            evidence_count += 1
            negative_count += 1
            last_confirmed_at = now
            if confidence < 0.2:
                is_archived = True
        elif signal == "not_relevant":
            confidence = max(0.0, confidence - 0.05)
            negative_count += 1

        return self.repository.update_memory(
            memory.id,
            self.user_id,
            confidence=confidence,
            evidence_count=evidence_count,
            positive_count=positive_count,
            negative_count=negative_count,
            last_confirmed_at=last_confirmed_at,
            is_archived=is_archived,
        )

    def record_intervention_result(
        self,
        intervention: str,
        result: str,
        source_message_id: str | None = None,
    ) -> MemoryRecord:
        memory_type = "worked_before" if result == "helped" else "did_not_work"
        existing = self.repository.find_similar_memory(self.user_id, memory_type, intervention)
        if existing:
            signal: MemoryFeedback = "helped" if result == "helped" else "did_not_help"
            return self.update_memory_confidence(existing, signal)
        confidence = 0.85 if result == "helped" else 0.9
        positive_count = 1 if result == "helped" else 0
        negative_count = 1 if result != "helped" else 0
        last_confirmed_at = utc_now_iso() if result == "helped" else None
        return self.repository.create_memory(
            user_id=self.user_id,
            memory_type=memory_type,
            content=intervention,
            confidence=confidence,
            source="feedback",
            evidence_count=1,
            positive_count=positive_count,
            negative_count=negative_count,
            last_confirmed_at=last_confirmed_at,
        )

    def detect_contradictions(
        self,
        existing_memories: list[MemoryRecord],
        proposed_memory_updates: list[MemoryUpdateProposal],
    ) -> list[MemoryUpdateProposal]:
        adjusted = list(proposed_memory_updates)
        for proposal in proposed_memory_updates:
            if proposal.type not in {"pattern", "hypothesis"} or not proposal.content:
                continue
            proposal_tokens = tokenize(proposal.content)
            for memory in existing_memories:
                if memory.id == proposal.target_memory_id or memory.type not in {"pattern", "hypothesis"}:
                    continue
                overlap = len(proposal_tokens & tokenize(memory.content))
                if overlap >= 3 and memory.content.lower().startswith("user ") != proposal.content.lower().startswith("user "):
                    adjusted.append(
                        MemoryUpdateProposal(
                            action="update",
                            type=memory.type,
                            content=memory.content,
                            confidence=max(0.0, memory.confidence - 0.2),
                            reason="Potential contradiction detected.",
                            target_memory_id=memory.id,
                            related_memory_id=proposal.target_memory_id,
                            relation_type="contradicts",
                        )
                    )
        return adjusted

    def merge_duplicate_memories(
        self,
        proposed_memory_updates: list[MemoryUpdateProposal],
        existing_memories: list[MemoryRecord],
    ) -> list[MemoryUpdateProposal]:
        merged: list[MemoryUpdateProposal] = []
        for proposal in proposed_memory_updates:
            if proposal.action != "create" or proposal.type is None or proposal.content is None:
                merged.append(proposal)
                continue
            existing = self.repository.find_similar_memory(
                self.user_id,
                proposal.type,
                proposal.content,
            )
            if existing:
                merged.append(
                    MemoryUpdateProposal(
                        action="update",
                        type=proposal.type,
                        content=existing.content,
                        confidence=max(existing.confidence, proposal.confidence or existing.confidence),
                        reason="Merged duplicate memory proposal.",
                        target_memory_id=existing.id,
                        related_memory_id=proposal.related_memory_id,
                        relation_type=proposal.relation_type or "updates",
                    )
                )
                continue
            merged.append(proposal)
        return merged

    def build_compact_context_text(self, context: PersonalizationContext) -> str:
        lines: list[str] = []
        if context.goal:
            lines.append("User goal:")
            lines.extend(f"- {memory.content}" for memory in context.goal)
        if context.preferences or context.relevant_context:
            lines.append("Relevant personal context:")
            lines.extend(f"- {memory.content}" for memory in context.preferences)
            lines.extend(f"- {memory.content}" for memory in context.relevant_context)
        if context.worked_before:
            lines.append("Worked before:")
            lines.extend(
                f"- {memory.content} (confidence: {self._confidence_label(memory)})"
                for memory in context.worked_before
            )
        if context.did_not_work:
            lines.append("Did not work:")
            lines.extend(
                f"- {memory.content} (confidence: {self._confidence_label(memory)})"
                for memory in context.did_not_work
            )
        if context.hypotheses:
            lines.append("Hypotheses to treat cautiously:")
            lines.extend(
                f"- {memory.content} (confidence: {self._confidence_label(memory)})"
                for memory in context.hypotheses
            )
        return "\n".join(lines) if lines else "No strong personalization context yet."

    @staticmethod
    def _confidence_label(memory: MemoryRecord) -> str:
        if memory.confidence >= 0.85:
            return "high"
        if memory.confidence >= 0.6:
            return "medium"
        return "low"

    def find_best_memory_match(self, message: str, memories: list[MemoryRecord]) -> MemoryRecord | None:
        message_tokens = tokenize(message)
        best: tuple[int, MemoryRecord] | None = None
        for memory in memories:
            overlap = len(message_tokens & tokenize(memory.content))
            if overlap == 0:
                continue
            if best is None or overlap > best[0]:
                best = (overlap, memory)
        return best[1] if best else None

    def infer_preference_or_constraint(self, message: str) -> MemoryCreateRequest | None:
        lowered = message.strip().lower()
        if lowered.startswith("remember that "):
            content = message.strip()[len("Remember that ") :]
            return MemoryCreateRequest(
                type="preference",
                content=f"User says: {content}",
                confidence=0.9,
                source="user_request",
                evidence_count=1,
                positive_count=1,
                last_confirmed_at=utc_now_iso(),
            )
        return None
