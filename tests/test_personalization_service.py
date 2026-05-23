from app.models.extractor import MemoryUpdateProposal
from app.models.memory import MemoryCreateRequest
from app.repositories.memory_repository import MemoryRepository
from app.services.memory_service import MemoryService
from app.services.personalization_service import PersonalizationService


def build_service(tmp_path):
    repository = MemoryRepository(str(tmp_path / "personalization.db"))
    memory_service = MemoryService(repository, "default_user")
    memory_service.ensure_seed_memories()
    personalization = PersonalizationService(repository, "default_user")
    return memory_service, personalization


def test_relevant_memory_ranking_prioritizes_matching_items(tmp_path):
    memory_service, personalization = build_service(tmp_path)
    memory_service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Morning light helped the user get out of bed.",
            confidence=0.9,
            source="manual",
        )
    )
    memory_service.create_memory(
        MemoryCreateRequest(
            type="pattern",
            content="User likes reading fiction before bed.",
            confidence=0.5,
            source="manual",
        )
    )

    ranked = personalization.rank_memories(
        memory_service.list_memories(),
        "I am struggling to get out of bed in the morning.",
    )
    assert "Morning light helped" in ranked[0].content


def test_compact_personalization_context_is_not_raw_dump(tmp_path):
    memory_service, personalization = build_service(tmp_path)
    memory_service.create_memory(
        MemoryCreateRequest(
            type="hypothesis",
            content="Late caffeine may be linked to early awakenings.",
            confidence=0.4,
            source="manual",
        )
    )
    context = personalization.get_personalization_context(
        "I woke up too early again.",
        memory_service.list_memories(),
    )
    text = personalization.build_compact_context_text(context)
    assert "User goal:" in text
    assert "Hypotheses to treat cautiously:" in text
    assert "fixed_goal:" not in text


def test_user_correction_reduces_confidence_or_archives_memory(tmp_path):
    memory_service, personalization = build_service(tmp_path)
    memory = memory_service.create_memory(
        MemoryCreateRequest(
            type="hypothesis",
            content="Late caffeine may be linked to early awakenings.",
            confidence=0.3,
            source="manual",
        )
    )
    updated = personalization.update_memory_confidence(memory, "wrong")
    assert updated.confidence <= 0.1 or updated.is_archived is True


def test_duplicate_memories_are_merged_into_update_proposals(tmp_path):
    memory_service, personalization = build_service(tmp_path)
    existing = memory_service.create_memory(
        MemoryCreateRequest(
            type="preference",
            content="User prefers concise advice.",
            confidence=0.9,
            source="manual",
        )
    )
    merged = personalization.merge_duplicate_memories(
        [
            MemoryUpdateProposal(
                action="create",
                type="preference",
                content="User prefers concise advice",
                confidence=0.85,
                reason="duplicate",
            )
        ],
        memory_service.list_memories(),
    )
    assert merged[0].action == "update"
    assert merged[0].target_memory_id == existing.id
