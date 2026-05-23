from app.models.extractor import MemoryExtractionResult, MemoryUpdateProposal
from app.models.memory import MemoryCreateRequest
from app.repositories.memory_repository import MemoryRepository
from app.services.memory_service import MemoryService


def build_service(tmp_path):
    repository = MemoryRepository(str(tmp_path / "memory.db"))
    service = MemoryService(repository, "default_user")
    service.ensure_seed_memories()
    return service


def test_validate_extractor_json_accepts_valid_update(tmp_path):
    service = build_service(tmp_path)
    result = MemoryExtractionResult(
        memory_updates=[
            MemoryUpdateProposal(
                action="create",
                type="worked_before",
                content="Morning light helped the user get out of bed.",
                confidence=0.9,
                reason="User explicitly said it helped.",
            )
        ],
        ignored=[],
    )

    validated = service.validate_extraction_result(result)
    assert len(validated.memory_updates) == 1


def test_validate_extractor_json_rejects_temporary_memory(tmp_path):
    service = build_service(tmp_path)
    result = MemoryExtractionResult(
        memory_updates=[
            MemoryUpdateProposal(
                action="create",
                type="pattern",
                content="User went to bed late last night.",
                confidence=0.7,
                reason="Observed in latest message.",
            )
        ],
        ignored=[],
    )

    validated = service.validate_extraction_result(result)
    assert validated.memory_updates == []
    assert validated.ignored


def test_apply_memory_updates_creates_memory(tmp_path):
    service = build_service(tmp_path)
    validated = MemoryExtractionResult(
        memory_updates=[
            MemoryUpdateProposal(
                action="create",
                type="did_not_work",
                content="Using many alarms did not help the user.",
                confidence=0.95,
                reason="User explicitly said it did not help.",
            )
        ],
        ignored=[],
    )

    applied = service.apply_memory_updates(validated)
    assert len(applied) == 1
    assert applied[0].type == "did_not_work"


def test_mark_memories_used_updates_last_used_at(tmp_path):
    service = build_service(tmp_path)
    memory = service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Morning light helped before.",
            confidence=0.9,
            source="manual",
        )
    )
    service.mark_memories_used([memory])
    refreshed = service.list_memories(include_archived=False)
    touched = next(item for item in refreshed if item.id == memory.id)
    assert touched.last_used_at is not None


def test_that_helped_updates_worked_before_memory(tmp_path):
    service = build_service(tmp_path)
    memory = service.record_intervention_feedback("Morning light helped after waking.", "helped")
    assert memory.type == "worked_before"
    assert memory.positive_count >= 1


def test_that_did_not_work_updates_did_not_work_memory(tmp_path):
    service = build_service(tmp_path)
    memory = service.record_intervention_feedback("Setting many alarms.", "did_not_help")
    assert memory.type == "did_not_work"
    assert memory.negative_count >= 1
