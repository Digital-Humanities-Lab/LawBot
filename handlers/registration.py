from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import logging
from datetime import datetime
from database.database_support import (
    update_user_conversation_state,
    update_user_email,
    get_verification_code,
    get_user_email,
    get_conversation_state,
    reset_user_registration
)
from mail.mail_confirmation import send_email
from utils.generate_verification_code import generate_verification_code
from utils.constants import (
    STARTED,
    AWAITING_EMAIL,
    AWAITING_VERIFICATION_CODE,
    VERIFIED
)

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