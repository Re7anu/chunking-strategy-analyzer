from fastapi import APIRouter, HTTPException, status, Depends
import bcrypt

from src.auth.jwt_handler import create_token
from src.auth.dependencies import get_current_user
from src.auth.models import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserContext,
    UserProfileResponse,
)
from src.db.user_store import (
    create_user,
    get_user_by_email,
    create_session,
    delete_session,
)
from src.auth.validators import validate_registration

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    """
    POST /api/auth/register
    Creates a new user with a bcrypt-hashed password, opens a session, and returns a JWT.
    """
    # Run constraints validation
    validate_registration(body)

    # Check for duplicate email
    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = create_user(body.username, body.email, password_hash)
    session = create_session(user["id"], body.session_name)
    token = create_token(str(user["id"]), str(session["id"]))

    return AuthResponse(
        token=token,
        user_id=str(user["id"]),
        session_id=str(session["id"]),
        username=user["username"],
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest):
    """
    POST /api/auth/login
    Verifies credentials, creates a new session, and returns a JWT.
    """
    user = get_user_by_email(body.email)
    if not user or not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    session = create_session(user["id"], body.session_name)
    token = create_token(str(user["id"]), str(session["id"]))

    return AuthResponse(
        token=token,
        user_id=str(user["id"]),
        session_id=str(session["id"]),
        username=user["username"],
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(user_context: UserContext = Depends(get_current_user)):
    """
    POST /api/auth/logout
    Deletes the current session row from PostgreSQL, invalidating the token server-side.
    """
    delete_session(user_context.session_id)
    return {"success": True, "message": "Logged out successfully."}


@router.get("/me", response_model=UserProfileResponse)
def me(user_context: UserContext = Depends(get_current_user)):
    """
    GET /api/auth/me
    Returns the current authenticated user's profile.
    """
    return UserProfileResponse(
        user_id=user_context.user_id,
        session_id=user_context.session_id,
        username=user_context.username,
        email=user_context.email,
    )
