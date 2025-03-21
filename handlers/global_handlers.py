import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database_support import user_exists, insert_user, delete_user_from_db, get_conversation_state
from utils.constants import STARTED, AWAITING_EMAIL, AWAITING_VERIFICATION_CODE, VERIFIED
from utils.state_map import STATE_MAP
from handlers.conversation import stage_one_conversation, stage_two_conversation, stage_three_conversation
from handlers.errors import send_error_message


async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """
    Global message handler that processes messages based on user's conversation state.
    
    Args:
        update (Update): The incoming update from Telegram
        context (ContextTypes.DEFAULT_TYPE): The context object for the handler
        
    Returns:
        Optional[int]: The current conversation state or None
    """
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else None

        if not chat_id:
            logging.error(f"Could not get chat_id for user {user_id}")
            return None

        logging.info(f"Processing message from user {user_id}")

        # Verify user existence
        if not await handle_new_user(context, chat_id, user_id):
            return None

        # Get current conversation state
        conversation_state = get_conversation_state(user_id)
        if not conversation_state:
            logging.error(f"Failed to get conversation state for user {user_id}")
            await send_error_message(context, chat_id)
            return None

        return await process_message_by_state(update, context, conversation_state, chat_id)

    except Exception as e:
        logging.exception(f"Error in global_message_handler: {str(e)}")
        if chat_id:
            await send_error_message(context, chat_id)
        return None


async def handle_new_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """
    Handle new users who haven't registered yet.
    
    Returns:
        bool: True if user exists, False otherwise
    """
    if not user_exists(user_id):
        logging.info(f"New unregistered user detected: {user_id}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Welcome! Please use the /start command to register first."
    )
        except Exception as e:
            logging.error(f"Failed to send message to new user: {str(e)}")
        return False
    return True


async def process_message_by_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    conversation_state: str,
    chat_id: int
    ) -> Optional[int]:
    """
    Process the message based on the user's conversation state.
    
    Returns:
        Optional[int]: The current conversation state or None
    """
    state_handlers = {
        "STARTED": handle_registration_state,
        "AWAITING_EMAIL": handle_registration_state,
        "AWAITING_VERIFICATION_CODE": handle_registration_state,
        "VERIFIED": handle_verified_state,
        "STAGE_1": stage_one_conversation,
        "STAGE_2": stage_two_conversation,
        "STAGE_3": stage_three_conversation
    }
    
    handler = state_handlers.get(conversation_state)
    
    if not handler:
        logging.warning(f"Unknown conversation state: {conversation_state}")
        try:
            print("unknown state")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Sorry, I encountered an unexpected state. Please use /start to reset."
            )
        except Exception as e:
            logging.error(f"Failed to send message for unknown state: {str(e)}")
            return None
    
    try:
        return await handler(update, context)
    except Exception as e:
        logging.exception(f"Error in state handler for state {conversation_state}: {str(e)}")
        await send_error_message(context, chat_id)
        return None


async def handle_registration_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handle users in registration states."""
    if not update.effective_chat:
        logging.error("No effective chat found in update")
        return None

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please complete your registration first."
        )
        return STATE_MAP.get(get_conversation_state(update.effective_user.id))
    except Exception as e:
        logging.error(f"Error in handle_registration_state: {str(e)}")
        return None


async def handle_verified_state(update: Update,context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """
    Handle verified users who haven't started any stage.
    
    Args:
        update: The update object from Telegram
        context: The context object from Telegram
    
    Returns:
        Optional[int]: The VERIFIED state constant or None if an error occurs
    """
    if not update.effective_chat:
        logging.error("No effective chat found in update")
        return None

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="You are verified and can now use the bot. Use /menu to configure your case."
        )
        return VERIFIED
    except Exception as e:
        logging.error(f"Error in handle_verified_state: {str(e)}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handler for the /start command. Manages user registration and verification flow.
    
    Args:
        update: Incoming update from Telegram
        context: Context object containing bot data
        
    Returns:
        int: The next conversation state
    """
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        logging.info(f"Start command received from user {user_id}")

        # Handle new user registration
        if not user_exists(user_id):
            return await handle_new_user_registration(user_id, chat_id, context)

        # Handle existing user based on their state
        conversation_state = get_conversation_state(user_id)
        if not conversation_state:
            logging.error(f"Failed to get conversation state for user {user_id}")
            await send_error_message(context, chat_id)
            return ConversationHandler.END

        return await handle_existing_user(update, conversation_state, chat_id, context)

    except Exception as e:
        logging.exception(f"Error in start handler: {str(e)}")
        await send_error_message(context, chat_id)
        return ConversationHandler.END


async def handle_new_user_registration(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle registration for new users."""
    try:
        # Insert new user with initial state
        insert_user(
            user_id=user_id,
            email=None,
            verification_code=None,
            conversation_state="STARTED"
            )
        logging.info(f"New user {user_id} registered with STARTED state")

        # Create registration button
        keyboard = [[InlineKeyboardButton("Register", callback_data="register")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! You need to register before using the bot. Please click the button below to register.",
            reply_markup=reply_markup
        )
        return STARTED

    except Exception as e:
        logging.exception(f"Error during new user registration: {str(e)}")
        await send_error_message(context, chat_id)
        return ConversationHandler.END


async def handle_existing_user(update: Update, conversation_state: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle interactions with existing users based on their conversation state."""
    try:
        state_handlers = {
            "STARTED": handle_started_state,
            "AWAITING_EMAIL": handle_awaiting_email_state,
            "AWAITING_VERIFICATION_CODE": handle_awaiting_verification_state,
            "VERIFIED": handle_verified_state,
            "STAGE_1": handle_verified_state,
            "STAGE_2": handle_verified_state,
            "STAGE_3": handle_verified_state
        }

        handler = state_handlers.get(conversation_state)
        if not handler:
            logging.warning(f"Unknown conversation state: {conversation_state}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Sorry, I encountered an unexpected state. Please contact support."
            )
            return ConversationHandler.END

        return await handler(update, context)

    except Exception as e:
        logging.exception(f"Error handling existing user: {str(e)}")
        await send_error_message(context, chat_id)
        return ConversationHandler.END


async def handle_started_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle users in STARTED state."""
    keyboard = [[InlineKeyboardButton("Register", callback_data="register")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="You've already started the process. Please register to continue.",
        reply_markup=reply_markup
    )
    return STARTED


async def handle_awaiting_email_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle users awaiting email verification."""
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_registration")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'.",
        reply_markup=reply_markup
    )
    return AWAITING_EMAIL


async def handle_awaiting_verification_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle users awaiting verification code."""
    keyboard = [
        [InlineKeyboardButton("Resend verification email", callback_data="resend_verification")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please enter the verification code sent to your email, or click below to resend the code.",
        reply_markup=reply_markup
    )
    return AWAITING_VERIFICATION_CODE


async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /delete command to remove user data."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Delete user data from the database
    delete_user_from_db(user_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text="Your data has been deleted. To start again, use the /start command.",
    )

    return ConversationHandler.END