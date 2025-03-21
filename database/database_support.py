import firebase_admin
from firebase_admin import credentials, firestore
from bot.config import load_config

config = load_config()

cred = credentials.Certificate('firebase.json')
firebase_admin.initialize_app(cred)

db = firestore.client()

def insert_user(user_id, email, verification_code, conversation_state='STARTED', case_data=None, issues=None, aspects=None):
    """Insert a new user into Firestore with the specified fields."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_data = {
            'email': email,
            'verification_code': verification_code,
            'conversation_state': conversation_state,
        }
        if case_data is not None:
            user_data['case_data'] = case_data
        if issues is not None:
            user_data['issues'] = issues
        if aspects is not None:
            user_data['aspects'] = aspects

        user_ref.set(user_data, merge=True)
    except Exception as e:
        print(f"Error inserting user: {e}")

def update_user_email(user_id, new_email, verification_code):
    """Update the user's email and verification code in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'email': new_email,
            'verification_code': verification_code,
            'conversation_state': 'AWAITING_VERIFICATION_CODE'
        })
    except Exception as e:
        print(f"Error updating email: {e}")

def update_user_conversation_state(user_id, conversation_state):
    """Update the user's conversation state in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'conversation_state': conversation_state
        })
    except Exception as e:
        print(f"Error updating conversation state: {e}")

def reset_user_registration(user_id):
    """Reset the user's registration data in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'email': firestore.DELETE_FIELD,
            'verification_code': firestore.DELETE_FIELD,
            'conversation_state': 'STARTED',
            'case_data': firestore.DELETE_FIELD,
            'issues': firestore.DELETE_FIELD,
            'aspects': firestore.DELETE_FIELD
        })
    except Exception as e:
        print(f"Error resetting user registration: {e}")

def get_conversation_state(user_id):
    """Get the user's conversation state from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('conversation_state')
        else:
            return None
    except Exception as e:
        print(f"Error fetching conversation state: {e}")
        return None

def get_user_email(user_id):
    """Get the user's email from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('email')
        else:
            return None
    except Exception as e:
        print(f"Error fetching user email: {e}")
        return None

def user_exists(user_id):
    """Check if the user exists in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        return user_ref.get().exists
    except Exception as e:
        print(f"Error checking if user exists: {e}")
        return False

def get_verification_code(user_id):
    """Get the verification code for the user from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('verification_code')
        else:
            return None
    except Exception as e:
        print(f"Error fetching verification code: {e}")
        return None

def delete_user_from_db(user_id):
    """Delete a user from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.delete()
    except Exception as e:
        print(f"Error deleting user: {e}")

def update_user_case_data(user_id, case_data):
    """Update the user's case data in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'case_data': case_data
        })
    except Exception as e:
        print(f"Error updating case data: {e}")

def get_user_case_data(user_id):
    """Get the user's case data from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('case_data')
        else:
            return None
    except Exception as e:
        print(f"Error fetching case data: {e}")
        return None

def update_user_issues(user_id, issues):
    """Update the user's issues in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'issues': issues
        })
    except Exception as e:
        print(f"Error updating issues: {e}")

def get_user_issues(user_id):
    """Get the user's issues from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('issues')
        else:
            return None
    except Exception as e:
        print(f"Error fetching issues: {e}")
        return None

def update_user_aspects(user_id, aspects):
    """Update the user's aspects of legality and proportionality in Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'aspects': aspects
        })
    except Exception as e:
        print(f"Error updating aspects: {e}")

def get_user_aspects(user_id):
    """Get the user's aspects of legality and proportionality from Firestore."""
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict().get('aspects')
        else:
            return None
    except Exception as e:
        print(f"Error fetching aspects: {e}")
        return None