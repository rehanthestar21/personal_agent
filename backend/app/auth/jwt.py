from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, get_settings

_bearer = HTTPBearer()


def create_access_token(device_id: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": device_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(device_id: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {"sub": device_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def require_auth(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate access token and return the device_id."""
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        device_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if device_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        return device_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
