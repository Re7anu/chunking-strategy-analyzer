import re
from fastapi import HTTPException, status
from src.auth.models import RegisterRequest
from src.config.settings import EMAIL_VALIDATION_PATTERN

EMAIL_REGEX = re.compile(EMAIL_VALIDATION_PATTERN)


def validate_registration(body: RegisterRequest):
    # Validate email format
    if not EMAIL_REGEX.match(body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address (e.g. user@domain.com)."
        )

    password = body.password
    # Validate length
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )
    # Validate uppercase
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter."
        )
    # Validate lowercase
    if not any(c.islower() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter."
        )
    # Validate number
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one digit."
        )
    # Validate special character (non-alphanumeric, non-space)
    if not any(not c.isalnum() and not c.isspace() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one special character (e.g. !@#$%^&*)."
        )
