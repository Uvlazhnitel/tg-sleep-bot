import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.core.config import get_settings
from app.services.chat_runtime import generate_chat_reply
from app.telegram_bot.handlers import TelegramBotHandlers

logger = logging.getLogger(__name__)


def build_reply_callback():
    def callback(
        user_id: str,
        message: str,
        history,
        session_id: str,
    ) -> str:
        response = generate_chat_reply(
            user_id=user_id,
            message=message,
            history=history,
            session_id=session_id,
            response_language="Russian",
        )
        return response.reply

    return callback


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot.")
    if settings.telegram_mode != "polling":
        raise RuntimeError(
            "Only TELEGRAM_MODE=polling is supported right now. "
            "Webhook support can be added later via POST /telegram/webhook."
        )

    handlers = TelegramBotHandlers(
        generate_reply=build_reply_callback(),
        allowed_user_id=settings.telegram_allowed_user_id,
    )
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text)
    )
    return application


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    application = build_application()
    logger.info("Starting Telegram bot in polling mode")
    application.run_polling()


if __name__ == "__main__":
    main()
