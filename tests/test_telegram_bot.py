import asyncio
from types import SimpleNamespace

from app.telegram_bot.handlers import (
    ERROR_TEXT,
    HELP_TEXT,
    START_TEXT,
    TelegramBotHandlers,
)
from app.telegram_bot.user_mapping import telegram_user_to_internal_user_id


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self) -> None:
        self.actions: list[tuple[int, str]] = []

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        self.actions.append((chat_id, action))


def run(coro) -> None:
    asyncio.run(coro)


def build_update(text: str, *, user_id: int = 42, chat_id: int = 1001):
    message = FakeMessage(text)
    return (
        SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
            effective_chat=SimpleNamespace(id=chat_id),
        ),
        message,
    )


def build_context(bot: FakeBot | None = None):
    return SimpleNamespace(bot=bot or FakeBot())


def test_telegram_user_id_maps_to_internal_user_id():
    assert telegram_user_to_internal_user_id(123456) == "telegram:123456"


def test_start_returns_expected_text():
    handlers = TelegramBotHandlers(generate_reply=lambda *_: "unused")
    update, message = build_update("/start")

    run(handlers.start(update, build_context()))

    assert message.replies == [START_TEXT]


def test_help_returns_expected_text():
    handlers = TelegramBotHandlers(generate_reply=lambda *_: "unused")
    update, message = build_update("/help")

    run(handlers.help(update, build_context()))

    assert message.replies == [HELP_TEXT]


def test_free_form_handler_calls_chat_service():
    calls: list[tuple[str, str, list, str]] = []

    def fake_generate_reply(user_id: str, message: str, history: list, session_id: str) -> str:
        calls.append((user_id, message, history, session_id))
        return "Try getting bright light soon after waking."

    handlers = TelegramBotHandlers(generate_reply=fake_generate_reply)
    update, message = build_update("I keep pressing snooze.")
    context = build_context()

    run(handlers.handle_text(update, context))

    assert calls == [
        ("telegram:42", "I keep pressing snooze.", [], "telegram-chat:1001")
    ]
    assert message.replies == ["Try getting bright light soon after waking."]
    assert context.bot.actions


def test_free_form_handler_handles_errors_gracefully():
    def fake_generate_reply(user_id: str, message: str, history: list, session_id: str) -> str:
        raise RuntimeError("boom")

    handlers = TelegramBotHandlers(generate_reply=fake_generate_reply)
    update, message = build_update("I can't sleep.")

    run(handlers.handle_text(update, build_context()))

    assert message.replies == [ERROR_TEXT]
