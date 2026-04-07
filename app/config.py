import os
import sys
from dotenv import load_dotenv

load_dotenv()


class Config:
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    TOGETHERAI_API_KEY = os.getenv("TOGETHERAI_API_KEY")
    DIMENSION = 1024
    CHUNK_SIZE = 500
    PINECONE_CLOUD = "aws"
    PINECONE_REGION = "us-east-1"

    # Auth config
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

    # Admin credentials from env (fallback to defaults for dev only)
    HOST_USERNAME = os.getenv("HOST_USERNAME", "host_admin")
    HOST_PASSWORD = os.getenv("HOST_PASSWORD")

    # Upload limits
    MAX_UPLOAD_SIZE_MB = 10
    MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @classmethod
    def validate_env_vars(cls):
        if not cls.COHERE_API_KEY:
            raise ValueError("COHERE_API_KEY not found in environment")
        if not cls.PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not found in environment")
        if not cls.JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY not found in environment. "
                "Set a strong random secret in your .env file."
            )
        if not cls.HOST_PASSWORD:
            raise ValueError(
                "HOST_PASSWORD not found in environment. "
                "Set a strong admin password in your .env file."
            )
