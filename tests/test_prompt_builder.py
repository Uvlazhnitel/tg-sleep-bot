from app.models.knowledge import KnowledgeCard
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
        ],
        [
            KnowledgeCard(
                id="kc1",
                topic="stable_wake_time",
                title="Stable wake time",
                claim="A stable wake time helps anchor the schedule.",
                practical_rule="Keep the target wake time stable after a late night.",
                when_to_use="Use when the user had a late bedtime.",
                avoid_advising="Do not suggest large sleep-ins.",
                evidence_level="strong",
                source_name="Sleep Foundation",
                source_url="https://example.com",
                tags=["wake_time", "schedule"],
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
                active=True,
            )
        ],
    )

    assert "09:00" in instructions
    assert "Use memories only when relevant" in instructions
    assert "phrase it as a possibility" in instructions
    assert "hypothesis" in instructions
    assert "Late caffeine may be associated with early awakenings" in instructions
    assert "Relevant Knowledge Cards" in instructions
    assert "stable_wake_time" in instructions
    assert "do not quote or expose source urls" in instructions.lower()
    assert "recommend professional help" in instructions
