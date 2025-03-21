import logging
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    PicklePersistence,
)

from utils.config import load_config
from handlers.conversation import *
from handlers.global_handlers import *
from handlers.registration import *

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot initialization...")  

    persistence = PicklePersistence(filepath='data')
    logger.info("Persistence initialized")

    # Load configuration
    config = load_config()
    logger.info("Configuration loaded successfully")

    async  def post_init(application: Application):
        application.bot_data['config'] = config
        logger.info("Config added to bot_data in post_init")

    # Create the Application and pass it your bot's token from config.txt
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).persistence(persistence).post_init(post_init).build()
    logger.info("Application instance created")

    application.bot_data['config'] = config
    # Register command handlers
    application.add_handler(CommandHandler("delete", delete_user))
    logger.info("Registered delete command handler")

    # Define the conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler('menu', send_main_menu),
            CallbackQueryHandler(register, pattern="^register$"),
        ],
        states={
            STARTED: [
                CallbackQueryHandler(register, pattern='^register$'),
            ],
            AWAITING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email),
                CallbackQueryHandler(cancel_registration, pattern='^cancel_registration$'),
            ],
            AWAITING_VERIFICATION_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code),
                CallbackQueryHandler(resend_verification, pattern='^resend_verification$'),
                CallbackQueryHandler(cancel_registration, pattern='^cancel_registration$'),
            ],
            VERIFIED: [
                CommandHandler('menu', send_main_menu),
                CallbackQueryHandler(go_to_first_stage, pattern='^start_stage_1$'),
            ],
            AWAITING_CASE: [
                MessageHandler(
                    (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
                    receive_case
                ),
            ],
            STAGE_1: [
                CommandHandler('menu', send_main_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stage_one_conversation),
                CallbackQueryHandler(go_to_first_stage, pattern='^start_stage_1$'),
                CallbackQueryHandler(go_to_second_stage, pattern='^start_stage_2$'),
            ],
            AWAITING_ISSUES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_issues),
            ],
            STAGE_2: [
                CommandHandler('menu', send_main_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stage_two_conversation),
                CallbackQueryHandler(go_to_first_stage, pattern='^start_stage_1$'),
                CallbackQueryHandler(go_to_second_stage, pattern='^start_stage_2$'),
                CallbackQueryHandler(go_to_third_stage, pattern='^start_stage_3$'),
            ],
            AWAITING_ASPECTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aspects),
            ],
            STAGE_3: [
                CommandHandler('menu', send_main_menu),
                CallbackQueryHandler(go_to_first_stage, pattern='^start_stage_1$'),
                CallbackQueryHandler(go_to_second_stage, pattern='^start_stage_2$'),
                CallbackQueryHandler(go_to_third_stage, pattern='^start_stage_3$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$"),
        ],
        per_chat=True,
        allow_reentry=True,
        name="Conversation", 
        persistent=True,     
    )
    logger.info("Conversation handler created")

    # Register the conversation handler
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))
    logger.info("All handlers registered successfully")

    # Run the bot
    logger.info("Starting bot polling...")
    application.run_polling()
    logger.info("Bot polling stopped")


if __name__ == "__main__":
    main()
