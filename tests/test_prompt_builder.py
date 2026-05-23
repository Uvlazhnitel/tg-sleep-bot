from app.models.knowledge import KnowledgeCard
from app.models.safety import SafetyClassification, SafetyRedFlag
from app.services.prompt_builder import build_assistant_instructions


def test_prompt_includes_fixed_profile_and_safety_rules():
    instructions = build_assistant_instructions(
        "\n".join(
            [
                "User goal:",
                "- User wants to wake up every day at 09:00.",
                "Hypotheses to treat cautiously:",
                "- Late caffeine may be associated with early awakenings for this user. (confidence: low)",
            ]
        ),
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
        SafetyClassification(
            category="C",
            red_flags=[
                SafetyRedFlag(
                    type="possible_sleep_apnea",
                    evidence="User mentioned waking up gasping.",
                    severity="medical_red_flag",
                )
            ],
            should_recommend_professional_help=True,
            should_prioritize_immediate_safety=False,
            assistant_guidance="Recommend professional evaluation and avoid diagnosis.",
        ),
    )

    assert "09:00" in instructions
    assert "Personalization Context" in instructions
    assert "use personalization only when relevant" in instructions.lower()
    assert "phrase it as a possibility" in instructions
    assert "hypotheses to treat cautiously" in instructions.lower()
    assert "Late caffeine may be associated with early awakenings" in instructions
    assert "Relevant Knowledge Cards" in instructions
    assert "stable_wake_time" in instructions
    assert "do not quote or expose source urls" in instructions.lower()
    assert "recommend professional help" in instructions
    assert "Safety Classification" in instructions
    assert "possible_sleep_apnea" in instructions
    assert "never recommend alcohol as a sleep aid" in instructions.lower()
