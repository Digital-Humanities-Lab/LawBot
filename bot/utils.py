import random

def generate_verification_code(length=6) -> str:
    """Generate a random numeric verification code."""
    return ''.join(random.choice('0123456789') for _ in range(length))
