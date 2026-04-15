from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.jwt import create_access_token, create_refresh_token, require_auth
from app.config import Settings, get_settings
from jose import JWTError, jwt

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class DeviceRegisterRequest(BaseModel):
    device_id: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/device", response_model=TokenResponse)
async def register_device(
    body: DeviceRegisterRequest,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    if settings.allowed_device_ids and body.device_id not in settings.allowed_device_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not authorized",
        )

    return TokenResponse(
        access_token=create_access_token(body.device_id, settings),
        refresh_token=create_refresh_token(body.device_id, settings),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshRequest,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        payload = jwt.decode(
            body.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        device_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if device_id is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )

    return TokenResponse(
        access_token=create_access_token(device_id, settings),
        refresh_token=create_refresh_token(device_id, settings),
    )
