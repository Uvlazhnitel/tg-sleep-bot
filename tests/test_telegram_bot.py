import asyncio
from types import SimpleNamespace

from app.telegram_bot.bot import build_reply_callback
from app.telegram_bot.handlers import (
    ACCESS_DENIED_TEXT,
    ERROR_TEXT,
    HELP_TEXT,
    START_TEXT,
    TelegramBotHandlers,
    VOICE_EMPTY_TRANSCRIPT_TEXT,
    VOICE_TRANSCRIPTION_ERROR_TEXT,
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


class FakeVoiceFile:
    def __init__(self, file_path: str = "voice.ogg") -> None:
        self.file_path = file_path
        self.download_paths: list[str] = []

    async def download_to_drive(self, custom_path=None, **kwargs):
        self.download_paths.append(str(custom_path))
        if custom_path is not None:
            with open(custom_path, "wb") as file_handle:
                file_handle.write(b"voice")
        return custom_path


class FakeVoice:
    def __init__(self, voice_file: FakeVoiceFile | None = None) -> None:
        self._voice_file = voice_file or FakeVoiceFile()

    async def get_file(self):
        return self._voice_file


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


def build_voice_update(*, user_id: int = 42, chat_id: int = 1001, voice_file: FakeVoiceFile | None = None):
    message = FakeMessage("")
    message.voice = FakeVoice(voice_file)
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


def test_unauthorized_user_is_blocked_before_chat_logic():
    calls: list[tuple[str, str, list, str]] = []

    def fake_generate_reply(user_id: str, message: str, history: list, session_id: str) -> str:
        calls.append((user_id, message, history, session_id))
        return "unused"

    handlers = TelegramBotHandlers(
        generate_reply=fake_generate_reply,
        allowed_user_id=417523636,
    )
    update, message = build_update("I keep pressing snooze.", user_id=999)
    context = build_context()

    run(handlers.handle_text(update, context))

    assert calls == []
    assert message.replies == [ACCESS_DENIED_TEXT]
    assert context.bot.actions == []


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


def test_telegram_reply_callback_forces_russian(monkeypatch):
    captured = {}

    def fake_generate_chat_reply(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(reply="Ответ")

    monkeypatch.setattr("app.telegram_bot.bot.generate_chat_reply", fake_generate_chat_reply)

    callback = build_reply_callback()
    reply = callback("telegram:42", "Mixed bilingual message", [], "telegram-chat:1001")

    assert reply == "Ответ"
    assert captured["response_language"] == "Russian"


def test_voice_handler_transcribes_and_calls_chat_service():
    calls: list[tuple[str, str, list, str]] = []

    def fake_generate_reply(user_id: str, message: str, history: list, session_id: str) -> str:
        calls.append((user_id, message, history, session_id))
        return "Текстовый ответ"

    handlers = TelegramBotHandlers(
        generate_reply=fake_generate_reply,
        transcribe_voice=lambda path: "Я очень поздно лёг вчера.",
    )
    update, message = build_voice_update()
    context = build_context()

    run(handlers.handle_voice(update, context))

    assert calls == [("telegram:42", "Я очень поздно лёг вчера.", [], "telegram-chat:1001")]
    assert message.replies == ["Текстовый ответ"]
    assert context.bot.actions


def test_voice_handler_blocks_unauthorized_user_before_transcription():
    calls: list[str] = []

    handlers = TelegramBotHandlers(
        generate_reply=lambda *_: "unused",
        transcribe_voice=lambda path: calls.append(path) or "unused",
        allowed_user_id=417523636,
    )
    update, message = build_voice_update(user_id=999)
    context = build_context()

    run(handlers.handle_voice(update, context))

    assert calls == []
    assert message.replies == [ACCESS_DENIED_TEXT]
    assert context.bot.actions == []


def test_voice_handler_returns_friendly_message_on_transcription_error():
    handlers = TelegramBotHandlers(
        generate_reply=lambda *_: "unused",
        transcribe_voice=lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    update, message = build_voice_update()

    run(handlers.handle_voice(update, build_context()))

    assert message.replies == [VOICE_TRANSCRIPTION_ERROR_TEXT]


def test_voice_handler_returns_retry_message_for_empty_transcript():
    handlers = TelegramBotHandlers(
        generate_reply=lambda *_: "unused",
        transcribe_voice=lambda path: "   ",
    )
    update, message = build_voice_update()

    run(handlers.handle_voice(update, build_context()))

    assert message.replies == [VOICE_EMPTY_TRANSCRIPT_TEXT]
