from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt

from src.config.settings import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_HOURS


def create_token(user_id: str, session_id: str) -> str:
    """
    Creates a signed JWT token encoding user_id and session_id.
    Token expires after JWT_EXPIRY_HOURS (default: 24 hours).
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": user_id,
        "session_id": session_id,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Validates and decodes a JWT token.
    Raises JWTError if the token is invalid or expired.
    Returns the full payload dict with 'sub' (user_id) and 'session_id'.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
