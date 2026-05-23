from app.models.reminder import ReminderCreateRequest, ReminderUpdateRequest
from app.repositories.reminder_repository import ReminderRepository


def test_create_update_delete_reminder(tmp_path):
    repository = ReminderRepository(str(tmp_path / "reminders.db"))
    reminder = repository.create_reminder(
        "default_user",
        ReminderCreateRequest(
            type="custom_sleep_reminder",
            title="Sleep reminder",
            message="Go to bed soon.",
            scheduled_time="2026-01-01T22:30:00+00:00",
            timezone="UTC",
        ),
    )

    assert reminder.active is True

    updated = repository.update_reminder(
        reminder.id,
        "default_user",
        ReminderUpdateRequest(active=False),
    )

    assert updated.active is False
    deleted = repository.delete_reminder(reminder.id, "default_user")
    assert deleted is not None
