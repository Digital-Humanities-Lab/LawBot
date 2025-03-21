import logging
from datetime import datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.utils import generate_verification_code
from bot.openai_client import openai_client
from database.database_support import (
    get_user_aspects,
    get_user_case_data,
    get_user_issues,
    insert_user,
    update_user_aspects,
    update_user_case_data,
    update_user_issues,
    user_exists,
    update_user_email,
    update_user_conversation_state,
    reset_user_registration,
    get_conversation_state,
    get_user_email,
    get_verification_code,
    delete_user_from_db,
)
from mail.mail_confirmation import send_email

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define stages for conversation
STARTED = 0
AWAITING_EMAIL = 1
AWAITING_VERIFICATION_CODE = 2
VERIFIED = 3
AWAITING_CASE = 4
STAGE_1 = 5
AWAITING_ISSUES = 6
STAGE_2 = 7
AWAITING_ASPECTS = 8
STAGE_3 = 9

# Mapping from state names to constants
STATE_MAP = {
    'STARTED': STARTED,
    'AWAITING_EMAIL': AWAITING_EMAIL,
    'AWAITING_VERIFICATION_CODE': AWAITING_VERIFICATION_CODE,
    'VERIFIED': VERIFIED,
    'AWAITING_CASE': AWAITING_CASE,
    'STAGE_1': STAGE_1,
    'AWAITING_ISSUES': AWAITING_ISSUES,
    'STAGE_2': STAGE_2,
    'AWAITING_ASPECTS': AWAITING_ASPECTS,
    'STAGE_3': STAGE_3,
    
}


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


async def send_error_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Send a generic error message to the user."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, an error occurred. Please try again or contact support if the issue persists."
        )
    except Exception as e:
        logging.error(f"Failed to send error message: {str(e)}")


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


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for the registration process."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Update user's state to 'AWAITING_EMAIL'
    update_user_conversation_state(user_id, "AWAITING_EMAIL")

    # Include cancel button
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_registration")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Prompt the user to enter their email
    await query.edit_message_text(
        text="Please enter your email address. It should be either '@ehu.lt' or '@student.ehu.lt'.",
        reply_markup=reply_markup,
    )

    return AWAITING_EMAIL


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the email."""
    user_id = update.message.from_user.id
    email = update.message.text.strip()
    logging.info(f"User {user_id} entered email: {email}")

    # Check if the email belongs to the allowed domains
    if not (email.endswith('@ehu.lt') or email.endswith('@student.ehu.lt')):
        logging.warning(f"Invalid email entered by user {user_id}: {email}")

        # Include cancel button
        keyboard = [[InlineKeyboardButton("Cancel", callback_data='cancel_registration')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Invalid email! Please make sure your email is either '@ehu.lt' or '@student.ehu.lt'. Try again.",
            reply_markup=reply_markup
        )
        return AWAITING_EMAIL

    # Generate verification code
    verification_code = generate_verification_code()
    logging.info(f"Generated verification code for user {user_id}: {verification_code}")

    # Update the user's email and verification code in the database
    try:
        update_user_email(user_id, new_email=email, verification_code=verification_code)
        logging.info(f"Updated email and verification code for user {user_id} in the database")
    except Exception as e:
        logging.exception(f"Exception updating user {user_id} in the database")
        await update.message.reply_text(
            "There was an error updating your information. Please try again later."
        )
        return ConversationHandler.END

    try:
        # Send the verification code via email
        send_email(email, verification_code)
        logging.info(f"Sent verification email to {email}")

        # Add buttons to resend the verification code and cancel
        keyboard = [
            [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
            [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Verification code sent to {email}. Please check your email and enter the code here.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE

    except Exception as e:
        logging.exception(f"Error sending verification email to {email}")
        await update.message.reply_text(
            "There was an error sending the verification email. Please try again later."
        )
        return ConversationHandler.END


async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for verifying the code."""
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()

    # Get the correct code from the database
    correct_code = get_verification_code(user_id)

    if correct_code is None:
        await update.message.reply_text("There was an issue retrieving your verification code. Please try again later.")
        return ConversationHandler.END

    if entered_code == str(correct_code):
        # Update the user's state to VERIFIED
        update_user_conversation_state(user_id, 'VERIFIED')

        await update.message.reply_text(
            "Your email has been verified! You can now use the bot.",
        )
        return VERIFIED
    else:
        keyboard = [
            [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
            [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Incorrect code. Please try again or click the button below to resend the verification email.",
            reply_markup=reply_markup
        )
        return AWAITING_VERIFICATION_CODE


async def resend_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for resending the verification email."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Get user's email from the database
    email = get_user_email(user_id)

    # Generate a new verification code
    verification_code = generate_verification_code()
    conversation_state = get_conversation_state(user_id)

    if conversation_state == 'VERIFIED':
        # User is already verified
        await query.edit_message_text("You're verified and can continue using the bot.")
        return ConversationHandler.END
    else:
        try:
            # Send the verification code to the user's email
            send_email(email, verification_code)

            # Update the verification code in the database
            update_user_email(user_id, email, verification_code)

            # Keep the same buttons
            keyboard = [
                [InlineKeyboardButton("Resend verification email", callback_data='resend_verification')],
                [InlineKeyboardButton("Cancel", callback_data='cancel_registration')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Add timestamp for uniqueness
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Edit the existing message with updated text
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"The verification code has been resent to {email} at {timestamp}. Please check your email.",
                reply_markup=reply_markup
            )

        except Exception as e:
            logging.exception("Exception in resend_verification handler")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Failed to resend verification email. Please try again later."
            )
            return ConversationHandler.END

        return AWAITING_VERIFICATION_CODE


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for canceling the registration."""
    query = update.callback_query
    user_id = query.from_user.id

    # Reset the user's registration data
    reset_user_registration(user_id)

    await query.answer()
    # Send a message indicating that registration has been canceled
    await query.edit_message_text(
        text="Registration has been canceled. To start again, please click the Register button.",
    )

    # Send the initial registration prompt with the Register button
    keyboard = [[InlineKeyboardButton("Register", callback_data='register')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Welcome! You need to register before using the bot. Please click the button below to register.",
        reply_markup=reply_markup
    )
    return STARTED


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_state = get_conversation_state(user_id)

    if conversation_state not in ['VERIFIED', 'STAGE_1', 'STAGE_2']:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please complete your registration first."
        )
        return

    keyboard = [
        [InlineKeyboardButton("Start Stage 1", callback_data="start_stage_1")],
        # Add other menu buttons here
    ]

    if conversation_state in ['STAGE_1', 'STAGE_2']:
        keyboard.append([InlineKeyboardButton("Proceed to Stage 2", callback_data="start_stage_2")])

    # If user is on Stage 2, add the option to proceed to Stage 3
    if conversation_state == 'STAGE_2':
        keyboard.append([InlineKeyboardButton("Proceed to Stage 3", callback_data="start_stage_3")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose an option:",
        reply_markup=reply_markup,
    )


async def go_to_first_stage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler when the user presses the 'Start Stage 1' button."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Update user's state to 'AWAITING_CASE'
    update_user_conversation_state(user_id, "AWAITING_CASE")

    # Prompt the user to enter their case
    await query.edit_message_text(
        text="Please enter the case for analysis:"
    )

    return AWAITING_CASE


async def go_to_second_stage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler when the user presses the 'Proceed to Stage 2' button."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Check if the user is eligible to proceed to Stage 2
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_1':
        await query.edit_message_text(
            text="You need to complete Stage 1 before proceeding to Stage 2."
        )
        return STAGE_1  # Return the current state instead of None

    # Update user's state to 'AWAITING_ISSUES'
    update_user_conversation_state(user_id, "AWAITING_ISSUES")

    # Prompt the user to enter the issues identified in Stage 1
    await query.edit_message_text(
        text="Please enter the issues identified in Stage 1:"
    )

    return AWAITING_ISSUES


async def go_to_third_stage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler when the user presses the 'Proceed to Stage 3' button."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Check if the user is eligible to proceed to Stage 3
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_2':
        await query.edit_message_text(
            text="You need to complete Stage 2 before proceeding to Stage 3."
        )
        return STAGE_2  # Return current state

    # Update user's state to 'AWAITING_ASPECTS'
    update_user_conversation_state(user_id, "AWAITING_ASPECTS")

    # Prompt the user to enter the aspects
    await query.edit_message_text(
        text="Please enter the aspects of legality and proportionality you will use:"
    )

    return AWAITING_ASPECTS


async def receive_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the case from the user."""
    user_id = update.effective_user.id
    case_text = update.message.text.strip()

    # Store the case in the database
    update_user_case_data(user_id, case_text)

    # Update conversation state to STAGE_1
    update_user_conversation_state(user_id, "STAGE_1")

    # Initialize conversation history for the user
    context.user_data['conversation_history'] = [
        {'role': 'system', 'content': 'You are a helpful assistant for legal case analysis.'},
        {'role': 'user', 'content': case_text}
    ]

    await update.message.reply_text(
        "Case received. You can now start the analysis. Please describe the issues you have identified."
    )

    return STAGE_1


async def receive_issues(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the issues from the user."""
    user_id = update.effective_user.id
    issues_text = update.message.text.strip()

    # Store the issues in the database
    update_user_issues(user_id, issues_text)

    # Update conversation state to STAGE_2
    update_user_conversation_state(user_id, "STAGE_2")

    # Initialize conversation history for the user
    # Retrieve previous conversation history from Stage 1
    if 'conversation_history' not in context.user_data:
        # If not present, initialize it with the case data
        case_text = get_user_case_data(user_id)
        context.user_data['conversation_history'] = [
            {'role': 'system', 'content': 'You are a helpful assistant for legal case analysis.'},
            {'role': 'user', 'content': case_text}
        ]

    # Add the issues to the conversation history
    context.user_data['conversation_history'].append({'role': 'user', 'content': issues_text})

    await update.message.reply_text(
        "Issues received. You can now start the analysis for Stage 2. Please proceed with identifying aspects of legality and proportionality."
    )

    return STAGE_2


async def receive_aspects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for receiving the aspects from the user."""
    user_id = update.effective_user.id
    aspects_text = update.message.text.strip()

    # Store the aspects in the database
    update_user_aspects(user_id, aspects_text)

    # Update conversation state to 'STAGE_3'
    update_user_conversation_state(user_id, "STAGE_3")

    await update.message.reply_text(
        "All aspects are defined. Now, please write your arguments answering the question:\n\n"
        "Do the authorities' decisions comply with the requirements of (1) legality and (2) proportionality?"
    )

    return STAGE_3


async def stage_one_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for GPT interaction during Stage 1."""
    user_id = update.effective_user.id
    user_message = update.message.text.strip()

    # Ensure the user is in the correct conversation state
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_1':
        await update.message.reply_text(
            "Please start Stage 1 first by selecting it from the menu."
        )
        return

    # Retrieve conversation history from user_data
    if 'conversation_history' not in context.user_data:
        # If not present, initialize it with the case data
        case_text = get_user_case_data(user_id)
        context.user_data['conversation_history'] = [
            {'role': 'system', 'content': 'You are a helpful assistant for legal case analysis.'},
            {'role': 'user', 'content': case_text}
        ]

    # Add the user's message to the conversation history
    context.user_data['conversation_history'].append({'role': 'user', 'content': user_message})

    # Prepare messages for OpenAI API
    messages = context.user_data['conversation_history']
    try:
        # Get the config from context.bot_data
        config = context.bot_data.get('config', {})
        gpt_model = config.get('GPT_MODEL', 'gpt-4o')
        # Call OpenAI API with streaming
        stream = openai_client.chat.completions.create(
            model=gpt_model,
            messages=messages,
            stream=True,
        )

        response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                response += delta.content

        # Check if the response is empty
        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")
        # Add assistant's reply to conversation history
        context.user_data['conversation_history'].append({'role': 'assistant', 'content': response})

        # Send assistant's reply to the user
        await update.message.reply_text(response)

    except Exception as e:
        logging.exception("Error during GPT interaction")
        await update.message.reply_text(
            "Sorry, there was an error processing your request."
        )

    return STAGE_1


async def stage_two_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for GPT interaction during Stage 2."""
    user_id = update.effective_user.id
    user_message = update.message.text.strip()

    # Ensure the user is in the correct conversation state
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_2':
        await update.message.reply_text(
            "Please start Stage 2 first by selecting it from the menu."
        )
        return

    # Retrieve conversation history from user_data
    if 'conversation_history' not in context.user_data:
        # If not present, initialize it with the case data and issues
        case_text = get_user_case_data(user_id)
        issues_text = get_user_issues(user_id)
        context.user_data['conversation_history'] = [
            {'role': 'system', 'content': 'You are a helpful assistant for legal case analysis focusing on aspects of legality and proportionality.'},
            {'role': 'user', 'content': case_text},
            {'role': 'user', 'content': issues_text}
        ]

    # Add the user's message to the conversation history
    context.user_data['conversation_history'].append({'role': 'user', 'content': user_message})

    # Prepare messages for OpenAI API
    messages = context.user_data['conversation_history']
    try:
        # Get the config from context.bot_data
        config = context.bot_data.get('config', {})
        gpt_model = config.get('GPT_MODEL', 'gpt-4')
        # Call OpenAI API with streaming
        stream = openai_client.chat.completions.create(
            model=gpt_model,
            messages=messages,
            stream=True,
        )

        response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                response += delta.content

        # Check if the response is empty
        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")
        # Add assistant's reply to conversation history
        context.user_data['conversation_history'].append({'role': 'assistant', 'content': response})

        # Send assistant's reply to the user
        await update.message.reply_text(response)

    except Exception as e:
        logging.exception("Error during GPT interaction in Stage 2")
        await update.message.reply_text(
            "Sorry, there was an error processing your request."
        )

    return STAGE_2


async def stage_three_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for GPT interaction during Stage 2."""
    user_id = update.effective_user.id
    user_message = update.message.text.strip()

    # Ensure the user is in the correct conversation state
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_3':
        await update.message.reply_text(
            "Please start Stage 2 first by selecting it from the menu."
        )
        return

    # Retrieve conversation history from user_data
    if 'conversation_history' not in context.user_data:
        # If not present, initialize it with the case data and issues
        case_text = get_user_case_data(user_id)
        issues_text = get_user_issues(user_id)
        aspects_text = get_user_aspects(user_id) 


        context.user_data['conversation_history'] = [
            {'role': 'system', 'content': 'You are a helpful assistant for legal case analysis focusing on aspects of legality and proportionality.'},
            {'role': 'user', 'content': case_text},
            {'role': 'user', 'content': issues_text},
            {'role': 'user', 'content': aspects_text}
        ]

    # Add the user's message to the conversation history
    context.user_data['conversation_history'].append({'role': 'user', 'content': user_message})

    # Prepare messages for OpenAI API
    messages = context.user_data['conversation_history']
    try:
        # Get the config from context.bot_data
        config = context.bot_data.get('config', {})
        gpt_model = config.get('GPT_MODEL', 'gpt-4')
        # Call OpenAI API with streaming
        stream = openai_client.chat.completions.create(
            model=gpt_model,
            messages=messages,
            stream=True,
        )

        response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if hasattr(delta, 'content') and delta.content:
                response += delta.content

        # Check if the response is empty
        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")
        # Add assistant's reply to conversation history
        context.user_data['conversation_history'].append({'role': 'assistant', 'content': response})

        # Send assistant's reply to the user
        await update.message.reply_text(response)

    except Exception as e:
        logging.exception("Error during GPT interaction in Stage 2")
        await update.message.reply_text(
            "Sorry, there was an error processing your request."
        )

    return STAGE_2


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

