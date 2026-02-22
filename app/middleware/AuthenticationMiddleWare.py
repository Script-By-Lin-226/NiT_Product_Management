from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.future import select
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from app.Model.datamodels import User
from app.Services.jwt_service import decode_token
from app.config.database_utils import async_session

PUBLIC_PATHS = {
    "/",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/authentication/login",
    "/authentication/register",
}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or _is_public_path(request.url.path):
            return await call_next(request)

        access_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header.split(" ", 1)[1]
        else:
            access_token = request.cookies.get("access_token")

        if access_token is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Authentication credentials were not provided."},
            )

        try:
            payload = await decode_token(access_token)
            subject = payload.get("sub")
            token_type = payload.get("type")

            if subject is None or token_type != "access":
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"message": "Invalid token."},
                )

            user_id = int(subject)

        except ExpiredSignatureError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Token expired."},
            )
        except (JWTError, ValueError):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Invalid token."},
            )

        async with async_session() as session:
            res = await session.execute(select(User).where(User.id == user_id))
            user = res.scalars().first()
            if user is None:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"message": "User not found."},
                )

        request.state.user = user
        request.state.credentials = payload
        return await call_next(request)

