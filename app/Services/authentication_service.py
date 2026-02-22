from typing import Optional

from fastapi import Request
from app.Services.jwt_service import create_access_token , create_refresh_token
from app.Services.password_hash import get_password_hash , verify_password
from starlette import status
from sqlalchemy.ext.asyncio import AsyncSession
from app.Model.datamodels import User
from app.Schemas.user_schemas import UserLogin , UserRegister
from sqlalchemy.future import select
from fastapi.responses import JSONResponse

async def check_existence(session:AsyncSession , email:str):
    check_user = select(User).where(User.email == email)
    res = await session.execute(check_user)
    existed_user = res.scalars().first()
    return existed_user is not None, existed_user



async def register_user(new_user:UserRegister, session:AsyncSession):
    check , existed_user = await check_existence(session, new_user.email)
    if check:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,content={"message":"Email already exists"}
        )
    registered_user = User(
        username=new_user.username,
        email=new_user.email,
        hash_password= await get_password_hash(new_user.password),
    )
    session.add(registered_user)
    await session.commit()
    await session.refresh(registered_user)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message":"User created successfully"}
    )

def _resolve_cookie_policy(request: Request | None) -> tuple[bool, str]:
    if request is None:
        return False, "lax"

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    scheme = forwarded_proto or request.url.scheme.lower()
    is_https = scheme == "https"
    return is_https, ("none" if is_https else "lax")


async def login(login_user:UserLogin , session:AsyncSession, request: Request | None = None):
    check  ,existed_user = await check_existence(session, login_user.email)
    if not check:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,content={"message":"User does not exist"})

    verified_user = await verify_password(login_user.password , existed_user.hash_password)
    if not verified_user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message":"Invalid Password"}
        )

    user_id_str = str(existed_user.id)
    access_token = await create_access_token({"sub":user_id_str , "type":"access"})
    refresh_token = await create_refresh_token({"sub":user_id_str , "type":"refresh"})
    response_object = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "Message":"Login Successfull"
        }
    )
    cookie_secure, cookie_samesite = _resolve_cookie_policy(request)
    response_object.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        samesite=cookie_samesite,
        secure=cookie_secure,
        path="/",
    )
    response_object.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        samesite=cookie_samesite,
        secure=cookie_secure,
        path="/",
    )
    response_object.headers["Authorization"] = f"Bearer {access_token}"
    response_object.headers["X-Refresh-Token"] = f"{refresh_token}"

    return response_object

async def forgot_password(request:Request, new_password: str, session:AsyncSession, email:Optional[str] | None):
    check_user = getattr(request.state, "user", None)
    if not check_user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message":"Authentication credentials were not provided."}
        )

    if email is not None and email != check_user.email:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"message":"You can only reset your own password."}
        )

    check_user.hash_password = await get_password_hash(new_password)
    session.add(check_user)
    await session.commit()
    await session.refresh(check_user)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message":"User successfully reset password!"
        }
    )

async def logout(request:Request):
    get_credential = request.cookies.get("access_token")
    if not get_credential:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message":"Authentication credentials were not provided."}
        )
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message":"You have successfully logged out"
        }
    )
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return response
