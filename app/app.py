from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config.database_utils import database_initialize
from app.api.v1 import auth_router
from app.api.v1 import product_router
from app.middleware.AuthenticationMiddleWare import AuthMiddleware

@asynccontextmanager
async def life_cycle(app:FastAPI):
    await database_initialize()
    yield

app = FastAPI(version="0.0.1", title="NITProductManagement", lifespan=life_cycle)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "https://ni-t-product-management.vercel.app",
    ],
    allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)*vercel\.app$|^https://([a-zA-Z0-9-]+\.)*ngrok-free\.(app|dev)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600
)

@app.get("/")
async def root():
    return {"message": "Hello World"}

app.include_router(auth_router.router)
app.include_router(product_router.router)
