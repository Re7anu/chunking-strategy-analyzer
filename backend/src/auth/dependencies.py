from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from src.auth.jwt_handler import decode_token
from src.db.user_store import get_user_by_id, get_session

# FastAPI's built-in Bearer token extractor
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> dict:
    """
    FastAPI dependency. Extracts and validates the Bearer JWT from the
    Authorization header. Returns a context dict with user_id, session_id,
    username, and email. Raises HTTP 401 on any failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
        session_id: str = payload.get("session_id")

        if not user_id or not session_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Verify user still exists in the database
    user = get_user_by_id(user_id)
    if not user:
        raise credentials_exception

    # Verify the session still exists (allows server-side logout/revocation)
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user["id"],
        "session_id": session["id"],
        "username": user["username"],
        "email": user["email"],
    }
