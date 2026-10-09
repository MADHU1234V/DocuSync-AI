"""Password hashing and signed bearer-token authentication."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import get_settings
from src.database import get_user_by_username

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_context.verify(password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, username: str) -> tuple[str, int]:
    settings = get_settings()
    settings.validate_auth()
    expires_in = settings.access_token_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "username": username, "iat": now,
               "exp": now + timedelta(seconds=expires_in), "jti": str(uuid4())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_in


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    settings = get_settings()
    settings.validate_auth()
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        username = payload.get("username")
        if not user_id or not username:
            raise unauthorized
    except JWTError as exc:
        raise unauthorized from exc
    user = get_user_by_username(username)
    if not user or user["id"] != user_id:
        raise unauthorized
    return {"id": user["id"], "username": user["username"]}
