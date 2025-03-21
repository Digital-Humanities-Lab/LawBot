from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging
from database.database_support import (
    get_conversation_state,
    update_user_conversation_state,
    update_user_case_data,
    update_user_issues,
    update_user_aspects,
    get_user_case_data,
    get_user_issues,
    get_user_aspects
)
from utils.extract_text import extract_text_from_doc, extract_text_from_pdf
from io import BytesIO
from utils.conversation_store import conversation_history
from utils.openai_client import openai_client
from utils.constants import STAGE_1, STAGE_2, STAGE_3, AWAITING_CASE, AWAITING_ISSUES, AWAITING_ASPECTS



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
        text="Please enter your case for analysis or upload a document (PDF, DOC, or DOCX):"
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
    """Handler for receiving the case from the user (text or document)."""
    user_id = update.effective_user.id
    
    # Clear conversation history for this user when starting stage 1
    if user_id in conversation_history:
        conversation_history[user_id] = []
    
    if update.message.document:
        # Get the document from the message
        document = update.message.document
        file = await context.bot.get_file(document.file_id)
        
        # Download the file
        file_bytes = BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
        
        # Extract text based on file type
        file_name = document.file_name.lower()
        try:
            if file_name.endswith('.pdf'):
                case_text = await extract_text_from_pdf(file_bytes)
            elif file_name.endswith(('.doc', '.docx')):
                case_text = await extract_text_from_doc(file_bytes)
            else:
                await update.message.reply_text(
                    "Sorry, I can only process PDF, DOC, or DOCX files. Please send your case in one of these formats or as a text message."
                )
                return AWAITING_CASE
        except Exception as e:
            logging.error(f"Error processing document: {str(e)}")
            await update.message.reply_text(
                "Sorry, I couldn't process your document. Please make sure it's a valid file or send your case as a text message."
            )
            return AWAITING_CASE
    else:
        # Handle text message
        case_text = update.message.text.strip()
    
    if not case_text:
        await update.message.reply_text(
            "I couldn't extract any text from your document. Please make sure it contains readable text or send your case as a text message."
        )
        return AWAITING_CASE
    
    # Store the case in the database and clear previous issues and aspects
    update_user_case_data(user_id, case_text)
    update_user_issues(user_id, "")  # Clear issues
    update_user_aspects(user_id, "")  # Clear aspects
    
    # Update conversation state to STAGE_1
    update_user_conversation_state(user_id, "STAGE_1")
    
    await update.message.reply_text(
        "Case received and processed. You can now start the analysis. Please describe the issues you have identified."
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

    if user_id in conversation_history:
        conversation_history[user_id] = []

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

    if user_id in conversation_history:
        conversation_history[user_id] = []

    await update.message.reply_text(
        "All aspects are defined. Now, please write your arguments answering the question:\n\n"
        "Do the authorities' decisions comply with the requirements of (1) legality and (2) proportionality?"
    )

    return STAGE_3


async def stage_one_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_message = update.message.text.strip() if update.message.text else None

    # Validate user message
    if not user_message:
        await update.message.reply_text(
            "It seems like your message is empty. Please provide valid input."
        )
        return STAGE_1

    # Ensure the user is in the correct conversation state
    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_1':
        await update.message.reply_text(
            "Please start Stage 1 first by selecting it from the menu."
        )
        return STAGE_1

    # Initialize conversation history if it doesn't exist
    if user_id not in conversation_history:
        conversation_history[user_id] = []
        # Add initial context only when starting fresh
    config = context.bot_data.get('config', {})
    system_prompt = config.get('SYSTEM_PROMPT_FIRST', '')
    user_case = get_user_case_data(user_id)
    
    # Add current user message
    conversation_history[user_id].append({"role": "user", "content": user_message})

    messages = [{"role": "system", "content": system_prompt}] + [{"role": "user", "content": user_case}] + conversation_history[user_id]
    
    try:
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

        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")

        # Append assistant's reply to conversation history
        conversation_history[user_id].append({"role": "assistant", "content": response})
        await update.message.reply_text(response)

    except ValueError as ve:
        logging.error(f"Validation error: {str(ve)}")
        await update.message.reply_text(
            "There was an error with the message format. Please try again."
        )
    except Exception as e:
        logging.exception("Error during GPT interaction")
        await update.message.reply_text(
            "Sorry, there was an error processing your request. Please try again."
        )

    return STAGE_1


async def stage_two_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_message = update.message.text.strip() if update.message.text else None

    if not user_message:
        await update.message.reply_text(
            "It seems like your message is empty. Please provide valid input."
        )
        return STAGE_2

    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_2':
        await update.message.reply_text(
            "Please start Stage 2 first by selecting it from the menu."
        )
        return STAGE_2

    # Initialize conversation history if it doesn't exist
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    config = context.bot_data.get('config', {})
    system_prompt = config.get('SYSTEM_PROMPT_SECOND', '')
    user_case = get_user_case_data(user_id)
    user_issues = get_user_issues(user_id)

    # Add current user message
    conversation_history[user_id].append({"role": "user", "content": user_message})
    
    messages = [{"role": "system", "content": system_prompt}] + [{"role": "user", "content": user_case}] + [{"role": "user", "content": user_issues}] + conversation_history[user_id]
    
    try:
        config = context.bot_data.get('config', {})
        gpt_model = config.get('GPT_MODEL', 'gpt-4')
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

        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")

        conversation_history[user_id].append({"role": "assistant", "content": response})
        await update.message.reply_text(response)

    except ValueError as ve:
        logging.error(f"Validation error: {str(ve)}")
        await update.message.reply_text(
            "There was an error with the message format. Please try again."
        )
    except Exception as e:
        logging.exception("Error during GPT interaction")
        await update.message.reply_text(
            "Sorry, there was an error processing your request. Please try again."
        )

    return STAGE_2


async def stage_three_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_message = update.message.text.strip() if update.message.text else None

    if not user_message:
        await update.message.reply_text(
            "It seems like your message is empty. Please provide valid input."
        )
        return STAGE_3

    conversation_state = get_conversation_state(user_id)
    if conversation_state != 'STAGE_3':
        await update.message.reply_text(
            "Please start Stage 3 first by selecting it from the menu."
        )
        return STAGE_3

    # Initialize conversation history if it doesn't exist
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    config = context.bot_data.get('config', {})
    system_prompt = config.get('SYSTEM_PROMPT_THIRD', '')
    user_case = get_user_case_data(user_id)
    user_issues = get_user_issues(user_id)
    user_aspects = get_user_aspects(user_id)

    # Add current user message
    conversation_history[user_id].append({"role": "user", "content": user_message})

    messages = [{"role": "system", "content": system_prompt}] + [{"role": "user", "content": user_case}] + [{"role": "user", "content": user_issues}] +[{"role": "user", "content": user_aspects}] + conversation_history[user_id]

    try:
        config = context.bot_data.get('config', {})
        gpt_model = config.get('GPT_MODEL', 'gpt-4')
        
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

        if not response.strip():
            raise ValueError("Received empty response from OpenAI API")

        conversation_history[user_id].append({"role": "assistant", "content": response})
        await update.message.reply_text(response)

    except ValueError as ve:
        logging.error(f"Validation error: {str(ve)}")
        await update.message.reply_text(
            "There was an error with the message format. Please try again."
        )
    except Exception as e:
        logging.exception("Error during GPT interaction")
        await update.message.reply_text(
            "Sorry, there was an error processing your request. Please try again."
        )

    return STAGE_3
