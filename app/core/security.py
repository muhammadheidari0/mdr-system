# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

SECRET_KEY = (settings.SECRET_KEY or "").strip()
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _ensure_secret_key() -> None:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set. Configure it in .env")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """????? ??? ??? ????"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """?? ???? ??? ????"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """???? JWT access token"""
    _ensure_secret_key()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
