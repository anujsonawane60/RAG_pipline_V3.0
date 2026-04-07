from typing import Optional
from pydantic import BaseModel


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    is_host: Optional[bool] = False


class UserInDB(User):
    hashed_password: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    is_host: Optional[bool] = False


class QueryRequest(BaseModel):
    model: str
    query: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "cohere",
                    "query": "What is the main topic of the document?",
                }
            ]
        }
    }
