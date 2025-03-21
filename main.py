from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

from bot.config import load_config
from bot.handlers import (
    AWAITING_ASPECTS,
    AWAITING_CASE,
    AWAITING_ISSUES,
    STAGE_1,
    STAGE_2,
    STAGE_3,
    STARTED,
    AWAITING_EMAIL,
    AWAITING_VERIFICATION_CODE,
    VERIFIED,
    go_to_first_stage,
    go_to_second_stage,
    go_to_third_stage,
    receive_aspects,
    receive_case,
    receive_issues,
    send_main_menu,
    stage_one_conversation,
    stage_two_conversation,
    start,
    register,
    cancel_registration,
    receive_email,
    verify_code,
    resend_verification,
    global_message_handler,
    delete_user,
)

filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)

def main() -> None:
    """Start the bot."""
    # Load configuration
    config = load_config()

    # Create the Application and pass it your bot's token from config.txt
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    application.bot_data['config'] = config

    # Register command handlers
    application.add_handler(CommandHandler("delete", delete_user))

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
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_case),
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
    )

    # Register the conversation handler
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))

    # Run the bot
    application.run_polling()


if __name__ == "__main__":
    main()
