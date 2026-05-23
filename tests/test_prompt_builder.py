from app.services.prompt_builder import build_phase1_instructions


def test_prompt_includes_fixed_profile_and_safety_rules():
    instructions = build_phase1_instructions()

    assert "wake up every day at 09:00" in instructions
    assert "does not want daily reports" in instructions
    assert "science-based" in instructions
    assert "snoozing alarms" in instructions
    assert "repeated time" in instructions
    assert "Do not diagnose medical conditions." in instructions
    assert "recommend professional help" in instructions
