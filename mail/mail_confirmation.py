import yagmail
import os
from utils.config import load_config
import minify_html

# Load configuration
config = load_config()
email_from = config["EMAIL_FROM"]
email_password = config["EMAIL_PASSWORD"]

def load_email_template(file_path, verification_code):
    """Loads the email template from a file and replaces placeholders."""
    with open(file_path, 'r') as file:
        template = minify_html.minify(file.read())

    # Replace placeholders with actual values
    return template.replace('{{ verification_code }}', str(verification_code))

def send_email(recipient_email, verification_code):
    """Sends an email with a verification code using Yagmail."""
    # Load the email template and replace placeholders
    template_path = "email_template.html"  # Path to your email template file
    html_body = load_email_template(template_path, verification_code)

    # Initialize Yagmail client
    yag = yagmail.SMTP(email_from, email_password)

    try:
        # Send the email
        yag.send(
            to=recipient_email,
            subject='Your Verification Code',
            contents=html_body
        )
        print(f"Verification email successfully sent to {recipient_email}")

    except Exception as e:
        print(f"An error occurred: {e}")
        raise Exception(f"Failed to send email: {e}")