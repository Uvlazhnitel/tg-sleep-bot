from app.models.memory import MemoryCreateRequest
from app.models.memory import MemoryUpdateRequest
from app.repositories.memory_repository import MemoryRepository
from app.services.memory_service import MemoryService


def test_create_list_archive_and_update_memory(tmp_path):
    repository = MemoryRepository(str(tmp_path / "test.db"))
    service = MemoryService(repository, "default_user")
    service.ensure_seed_memories()

    created = service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Morning light helped the user get out of bed.",
            confidence=0.9,
            source="manual",
        )
    )
    assert created.type == "worked_before"

    memories = service.list_memories()
    assert any(memory.id == created.id for memory in memories)

    updated = service.update_memory(
        created.id,
        MemoryUpdateRequest(
            content="Morning light helps with wake-ups.",
            confidence=0.95,
            source="manual",
        ),
    )
    assert updated.content == "Morning light helps with wake-ups."

    archived = service.archive_memory(created.id)
    assert archived.is_archived is True


def test_avoid_duplicate_memories(tmp_path):
    repository = MemoryRepository(str(tmp_path / "test.db"))
    service = MemoryService(repository, "default_user")
    service.ensure_seed_memories()

    first = service.create_memory(
        MemoryCreateRequest(
            type="preference",
            content="User prefers concise, practical advice.",
            confidence=0.9,
            source="manual",
        )
    )
    second = service.create_memory(
        MemoryCreateRequest(
            type="preference",
            content="User prefers concise practical advice.",
            confidence=0.85,
            source="manual",
        )
    )

    assert first.id == second.id


def test_get_relevant_memories_returns_ranked_subset_when_large(tmp_path):
    repository = MemoryRepository(str(tmp_path / "test.db"))
    service = MemoryService(repository, "default_user")
    service.ensure_seed_memories()

    for index in range(40):
        repository.create_memory(
            user_id="default_user",
            memory_type="pattern",
            content=f"Pattern memory {index} about caffeine" if index < 5 else f"Pattern memory {index} about something else",
            confidence=0.6,
            source="manual",
        )

    relevant = service.get_relevant_memories("caffeine wakes me early")
    assert len(relevant) == 20
    assert any("caffeine" in memory.content.lower() for memory in relevant[:5])
