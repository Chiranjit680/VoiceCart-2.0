import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .routers import cart, orders, product, user, search, reviews, categories, chat
from .database import engine
from .utils.chat_maintenance import maintenance_loop

models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Closes idle voice-chat sessions and deletes expired ones in the background.
    task = asyncio.create_task(maintenance_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

# Allow the Vite frontend to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router)
app.include_router(product.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(search.router)
app.include_router(reviews.router)
app.include_router(categories.router)
app.include_router(chat.router)

@app.get("/")
async def root():
    return {"message": "Welcome to VoiceCart!"}
