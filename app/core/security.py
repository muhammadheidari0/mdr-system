# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

SECRET_KEY = (settings.SECRET_KEY or "").strip()
ALGORITHM = settings.JWT_ALGORITHM
MAX_BCRYPT_PASSWORD_BYTES = 72


def _ensure_secret_key() -> None:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set. Configure it in .env")


def _validate_bcrypt_password_length(password: str) -> bytes:
    if password is None:
        raise ValueError("Password is required.")
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt {MAX_BCRYPT_PASSWORD_BYTES}-byte limit."
        )
    return encoded


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """????? ??? ??? ????"""
    if not plain_password or not hashed_password:
        return False
    try:
        plain_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bool(bcrypt.checkpw(plain_bytes, hashed_bytes))
    except (TypeError, ValueError, UnicodeError):
        return False


def get_password_hash(password: str) -> str:
    """?? ???? ??? ????"""
    password_bytes = _validate_bcrypt_password_length(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """???? JWT access token"""
    _ensure_secret_key()
    to_encode = data.copy()
    configured_minutes = max(1, int(settings.ACCESS_TOKEN_EXPIRE_MINUTES or 43200))
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=configured_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    """????? ?????? JWT token ? ?????????? email"""
    _ensure_secret_key()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        return email
    except JWTError:
        return None
