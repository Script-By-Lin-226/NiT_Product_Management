from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config.configuration import settings


async def create_access_token(credential: dict) -> str:
    data = credential.copy()
    expires_in = datetime.now(timezone.utc) + timedelta(minutes=settings.Access_Token_Expire)
    data.update({"exp": expires_in, "type": "access"})
    return jwt.encode(data, settings.Secret_Key, algorithm=settings.Algorithm)


async def create_refresh_token(credential: dict) -> str:
    data = credential.copy()
    expires_in = datetime.now(timezone.utc) + timedelta(days=settings.Refresh_Token_Expire)
    data.update({"exp": expires_in, "type": "refresh"})
    return jwt.encode(data, settings.Secret_Key, algorithm=settings.Algorithm)


async def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.Secret_Key, algorithms=[settings.Algorithm])

