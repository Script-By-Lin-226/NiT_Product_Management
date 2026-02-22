from jose import jwt, JWTError
from sqlalchemy.future import select
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.database_utils import async_session
from app.Model.datamodels import User
from app.Services.jwt_service import decode_token, create_access_token

_EXCLUDE_PATH = ["/authentication/login", "/authentication/register", "/openapi.json", "/docs", "/redoc", "/"]


class TokenRotationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Let preflight and public paths pass through untouched
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in _EXCLUDE_PATH:
            return await call_next(request)

        # Check for token in Authorization header first, then cookies
        access_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header.split(" ")[1]
        else:
            access_token = request.cookies.get("access_token")

        if not access_token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Access token is required"},
            )

        try:
            # This will raise jwt.ExpiredSignatureError when the access token is expired
            await decode_token(access_token)
            # Token is valid and not expired – continue down the stack
            return await call_next(request)

        except jwt.ExpiredSignatureError:
            # Try to rotate using refresh token
            refresh_token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
            if not refresh_token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Refresh token is required"},
                )

            try:
                refresh_payload = await decode_token(refresh_token)
                user_id = int(refresh_payload.get("sub")) if refresh_payload.get("sub") is not None else None
                token_type = refresh_payload.get("type")
                if user_id is None or token_type != "refresh":
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Invalid refresh token"},
                    )

                async with async_session() as session:
                    res = await session.execute(select(User).where(User.id == user_id))
                    user = res.scalars().first()
                    if not user:
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"detail": "User not found"},
                        )

                # Create new access token
                new_access_token = await create_access_token({"sub": str(user_id)})

                # Attach user to request so downstream handlers (e.g., auth middleware) can use it
                request.state.user = user

                response = await call_next(request)
                # Update cookies and headers with the new access token
                response.set_cookie(
                    "access_token",
                    new_access_token,
                    httponly=True,
                    samesite="lax",
                    max_age=30 * 60,
                )
                response.headers["Authorization"] = f"Bearer {new_access_token}"
                response.headers["X-New-Access-Token"] = new_access_token

                return response

            except JWTError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid refresh token"},
                )

        except JWTError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid access token"},
            )
