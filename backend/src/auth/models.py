from pydantic import BaseModel
from src.config.settings import DEFAULT_SESSION_NAME


# ─── Auth Request & Response Models ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    session_name: str = DEFAULT_SESSION_NAME


class LoginRequest(BaseModel):
    email: str
    password: str
    session_name: str = DEFAULT_SESSION_NAME


class AuthResponse(BaseModel):
    token: str
    user_id: str
    session_id: str
    username: str


class UserContext(BaseModel):
    user_id: str
    session_id: str
    username: str
    email: str


class UserProfileResponse(BaseModel):
    user_id: str
    session_id: str
    username: str
    email: str
