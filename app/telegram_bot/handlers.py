import logging
from collections import defaultdict, deque
from collections.abc import Callable

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.models.chat import HistoryMessage
from app.telegram_bot.user_mapping import telegram_user_to_internal_user_id

logger = logging.getLogger(__name__)

START_TEXT = (
    "Hi — I’m your sleep assistant. I’ll help you make practical sleep decisions "
    "around your goal of waking up at 09:00. Just write what’s going on, and I’ll "
    "suggest the best next step. I won’t ask for daily reports."
)

HELP_TEXT = (
    "Можешь писать свободно, например:\n"
    "- Я очень поздно лёг. Как восстановиться и не испортить завтрашний день?\n"
    "- Я проснулся раньше, чем планировал.\n"
    "- Я постоянно нажимаю snooze.\n"
    "- Я не могу заснуть.\n"
    "- Я устал, но всё равно хочу вставать в 09:00.\n\n"
    "Ещё можно спросить: Что ты помнишь обо мне?"
)

ERROR_TEXT = "Sorry, I couldn’t process that right now. Try again in a moment."
ACCESS_DENIED_TEXT = "Извини, этот бот доступен только владельцу."


class TelegramHistoryStore:
    def __init__(self, max_messages: int = 6) -> None:
        self.max_messages = max_messages
        self._history: dict[str, deque[HistoryMessage]] = defaultdict(
            lambda: deque(maxlen=self.max_messages)
        )

    def get(self, user_id: str) -> list[HistoryMessage]:
        return list(self._history[user_id])

    def append_turn(self, user_id: str, user_message: str, assistant_reply: str) -> None:
        history = self._history[user_id]
        history.append(HistoryMessage(role="user", content=user_message))
        history.append(HistoryMessage(role="assistant", content=assistant_reply))


class TelegramBotHandlers:
    def __init__(
        self,
        generate_reply: Callable[[str, str, list[HistoryMessage], str], str],
        history_store: TelegramHistoryStore | None = None,
        allowed_user_id: int | None = None,
    ) -> None:
        self.generate_reply = generate_reply
        self.history_store = history_store or TelegramHistoryStore()
        self.allowed_user_id = allowed_user_id

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self._is_allowed(update):
            if update.message is not None:
                await update.message.reply_text(ACCESS_DENIED_TEXT)
            return
        if update.message is not None:
            await update.message.reply_text(START_TEXT)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self._is_allowed(update):
            if update.message is not None:
                await update.message.reply_text(ACCESS_DENIED_TEXT)
            return
        if update.message is not None:
            await update.message.reply_text(HELP_TEXT)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None or chat is None or not message.text:
            return
        if not self._is_allowed(update):
            await message.reply_text(ACCESS_DENIED_TEXT)
            return

        internal_user_id = telegram_user_to_internal_user_id(user.id)
        session_id = f"telegram-chat:{chat.id}"
        history = self.history_store.get(internal_user_id)

        try:
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
            reply = self.generate_reply(
                internal_user_id,
                message.text,
                history,
                session_id,
            )
        except Exception:
            logger.exception("Telegram chat handler failed for user %s", user.id)
            await message.reply_text(ERROR_TEXT)
            return

        self.history_store.append_turn(internal_user_id, message.text, reply)
        await message.reply_text(reply)

    def _is_allowed(self, update: Update) -> bool:
        if self.allowed_user_id is None:
            return True
        user = update.effective_user
        return user is not None and user.id == self.allowed_user_id
