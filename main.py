import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pinecone import Pinecone

from app.config import Config
from app.auth import set_user_manager
from app.services.chatbot_manager import ChatbotManager
from app.services.user_manager import UserManager
from app.routes.auth_routes import router as auth_router
from app.routes.chatbot_routes import router as chatbot_router, set_chatbot_manager

# Validate configuration on startup
Config.validate_env_vars()

app = FastAPI(title="Multi-RAG Chatbot API")

# CORS — restrict origins in production via ALLOWED_ORIGINS env var
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*", "Authorization", "Content-Type"],
    expose_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize managers and wire them up
chatbot_manager = ChatbotManager()
user_manager = UserManager()
set_chatbot_manager(chatbot_manager)
set_user_manager(user_manager)

# Register routes
app.include_router(auth_router)
app.include_router(chatbot_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return f.read()


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    with open("static/admin.html", "r") as f:
        return f.read()


def test_pinecone_connection():
    try:
        pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        indexes = pc.list_indexes()
        print(
            f"Connected to Pinecone. Available indexes: "
            f"{[index.name for index in indexes]}"
        )
        return True
    except Exception as e:
        print(f"Failed to connect to Pinecone: {str(e)}")
        return False


if __name__ == "__main__":
    try:
        print("Starting server...")
        if not test_pinecone_connection():
            print("Failed to establish Pinecone connection.")
            sys.exit(1)

        os.makedirs("uploaded_files", exist_ok=True)
        os.makedirs("chat_history", exist_ok=True)

        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        print(f"Failed to start application: {str(e)}")
