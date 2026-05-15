import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings

_bearer = HTTPBearer(auto_error=True)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    settings = get_settings()
    if not secrets.compare_digest(credentials.credentials, settings.auth_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    return credentials.credentials
