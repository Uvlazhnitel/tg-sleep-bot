from app.models.insight import InsightCreateRequest, InsightPreferenceUpdateRequest, InsightUpdateRequest
from app.repositories.insight_repository import InsightRepository


def test_create_and_update_insight(tmp_path):
    repository = InsightRepository(str(tmp_path / "insights.db"))
    created = repository.create_insight(
        "default_user",
        InsightCreateRequest(
            title="Multiple alarms may reinforce snoozing",
            summary="Multiple alarms seem to make snoozing easier.",
            evidence=["User mentioned snoozing repeatedly."],
            confidence="high",
            suggested_experiment="For the next 3 mornings, use one main alarm only.",
        ),
    )

    assert created.status == "active"
    assert created.related_memory_ids == []

    updated = repository.update_insight(
        created.id,
        "default_user",
        InsightUpdateRequest(status="dismissed"),
    )

    assert updated.status == "dismissed"


def test_find_duplicate_insight(tmp_path):
    repository = InsightRepository(str(tmp_path / "insights.db"))
    repository.create_insight(
        "default_user",
        InsightCreateRequest(
            title="Late naps may be delaying sleep pressure",
            summary="Late naps may make it harder to fall asleep.",
            evidence=["User mentioned evening naps."],
            confidence="medium",
            suggested_experiment="Avoid late naps for the next few days.",
        ),
    )

    duplicate = repository.find_duplicate_insight(
        "default_user",
        "Late naps may be delaying sleep pressure",
        "Something else",
    )

    assert duplicate is not None


def test_preferences_persist(tmp_path):
    repository = InsightRepository(str(tmp_path / "insights.db"))
    initial = repository.get_preferences("default_user")
    assert initial.proactive_insights_enabled is True
    assert initial.insight_min_evidence_threshold == 5

    updated = repository.update_preferences(
        "default_user",
        InsightPreferenceUpdateRequest(proactive_insights_enabled=False),
    )

    assert updated.proactive_insights_enabled is False
