import logging
from telegram.ext import ContextTypes


async def send_error_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Send a generic error message to the user."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, an error occurred. Please try again or contact support if the issue persists."
        )
    except Exception as e:
        logging.error(f"Failed to send error message: {str(e)}")