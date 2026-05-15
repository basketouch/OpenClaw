import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from config import get_settings

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    settings = get_settings()
    ok_user = secrets.compare_digest(body.username, settings.auth_username)
    ok_pass = secrets.compare_digest(body.password, settings.auth_password)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    return LoginResponse(token=settings.auth_secret)
