from app.Services.authentication_service import register_user , login ,logout ,forgot_password
from app.Services.admin_service import is_admin_user
from fastapi import Depends , APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.config.database_utils import get_async_session
from app.Schemas.user_schemas import UserRegister , UserLogin
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter(prefix="/authentication", tags=["authentication"])

limiter = Limiter(key_func=get_remote_address)

@router.post("/register")
async def register_route(new_user: UserRegister, session: AsyncSession = Depends(get_async_session)):
    return await register_user(new_user,session)

@limiter.limit("10/per hour")
@router.post("/login")
async def login_route(user: UserLogin,request:Request, session: AsyncSession = Depends(get_async_session)):
    return await login(user, session, request)

@router.post("/forgot")
async def forgot_password_route(
    new_password: str,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    email: Optional[str] = None,
):
    return await forgot_password(request , new_password , session , email)

@router.post("/logout")
async def logout_route(request:Request):
    return await logout(request)


@router.get("/me")
async def current_user_route(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": is_admin_user(user),
    }
