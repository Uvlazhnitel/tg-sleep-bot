from app.models.memory import MemoryRecord
from app.services.prompt_builder import build_assistant_instructions


def test_prompt_includes_fixed_profile_and_safety_rules():
    instructions = build_assistant_instructions(
        [
            MemoryRecord(
                id="1",
                user_id="default_user",
                type="hypothesis",
                content="Late caffeine may be associated with early awakenings for this user.",
                confidence=0.4,
                source="manual",
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
                last_used_at=None,
                is_archived=False,
            )
        ]
    )

    assert "09:00 wake-up goal" in instructions
    assert "Use memories only when relevant" in instructions
    assert "phrase it as a possibility" in instructions
    assert "hypothesis" in instructions
    assert "Late caffeine may be associated with early awakenings" in instructions
    assert "recommend professional help" in instructions
