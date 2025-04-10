import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import cohere
import pinecone
from pinecone import Pinecone, ServerlessSpec
import uvicorn
import PyPDF2
import io
import docx
import re
import tempfile
import shutil
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union
import json
import openai
import together
import requests
from pydantic import BaseModel
import sys
from passlib.context import CryptContext
from jose import JWTError, jwt
import uuid

# Load environment variables
load_dotenv()

# JWT Settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password context for hashing - with backup option if bcrypt fails
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # Test bcrypt is working correctly
    test_hash = pwd_context.hash("test_password")
    pwd_context.verify("test_password", test_hash)
except Exception as e:
    print(f"Warning: bcrypt error - {str(e)}. Using fallback scheme")
    # Use sha256_crypt as fallback if bcrypt has issues
    pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

# OAuth2 bearer token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define User models
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
    # Admin role is only set via hardcoded credentials

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    is_host: Optional[bool] = False

# Host admin credentials (hardcoded as requested)
HOST_USERNAME = "host_admin"
HOST_PASSWORD = "admin123"  # In production, use a strong password

# In-memory user database (replace with a real database in production)
users_db = {}

# Function to verify password
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Function to get password hash
def get_password_hash(password):
    return pwd_context.hash(password)

# Create access token
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Get user from database
def get_user(username: str):
    print(f"Looking up user in database: {username}")
    return user_manager.get_user(username)

# Authenticate user
def authenticate_user(username: str, password: str):
    print(f"Authenticating user: {username}")
    return user_manager.authenticate_user(username, password)

# Get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Basic token format validation
        if not token or len(token) < 10:
            print("Token is missing or too short")
            raise credentials_exception
            
        # Print token for debugging (remove in production)
        token_prefix = token[:15] if len(token) >= 15 else token
        print(f"Validating token: {token_prefix}...")
        
        # Try to decode token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            print(f"Token payload: {payload}")
        except jwt.ExpiredSignatureError:
            print("Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.JWTError as e:
            print(f"JWT Error: {str(e)}")
            raise credentials_exception
        except Exception as e:
            print(f"Unexpected error decoding token: {str(e)}")
            raise credentials_exception
            
        # Extract username from token payload
        username: str = payload.get("sub")
        if username is None:
            print("Username missing from token")
            raise credentials_exception
        
        # Extract is_host from token payload
        is_host = payload.get("is_host", False)
        token_data = TokenData(username=username, is_host=is_host)
        
        print(f"Token validated for user: {username}, is_host: {is_host}")
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        raise credentials_exception
    
    # Get user from token data
    try:
        # Special case for host admin
        if token_data.username == HOST_USERNAME:
            print(f"Creating host admin user object")
            user = UserInDB(
                username=HOST_USERNAME,
                hashed_password=get_password_hash(HOST_PASSWORD),
                is_host=True,
                email="admin@example.com"
            )
        else:
            # Get regular user from database
            print(f"Looking up user in database: {token_data.username}")
            user = get_user(username=token_data.username)
        
        if user is None:
            print(f"User not found: {token_data.username}")
            raise credentials_exception
        
        # Convert from UserInDB to User to avoid serializing hashed password
        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            is_host=user.is_host or token_data.is_host
        )
    except Exception as e:
        print(f"User lookup error: {str(e)}")
        raise credentials_exception

# Get current active user
async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# Verify if user is host admin
async def get_host_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_host and current_user.username != HOST_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as host admin"
        )
    return current_user

app = FastAPI(title="Multi-RAG Chatbot API")

# Retrieve API keys from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
TOGETHERAI_API_KEY = os.getenv("TOGETHERAI_API_KEY")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*", "Authorization", "Content-Type"],
    expose_headers=["*"]
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class Config:
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    DIMENSION = 1024
    CHUNK_SIZE = 500
    PINECONE_CLOUD = "aws"
    PINECONE_REGION = "us-east-1"

    @classmethod
    def validate_env_vars(cls):
        if not cls.COHERE_API_KEY:
            raise ValueError("COHERE_API_KEY not found")
        if not cls.PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not found")

class QueryRequest(BaseModel):
    model: str
    query: str

    class Config:
        schema_extra = {
            "example": {
                "model": "cohere",  # or "openai" or "togetherai"
                "query": "What is the main topic of the document?"
            }
        }

class ServiceManager:
    def __init__(self):
        # Initialize cohere client
        self.co = None
        self.pc = None
        self.index = None
        self.active_index_name = None
        self.retry_attempts = 3
        
    def initialize_services(self, index_name: str):
        """Initialize Cohere and Pinecone services."""
        try:
            print("Initializing Pinecone...")
            
            if not Config.PINECONE_API_KEY:
                raise Exception("Pinecone API key is missing")
            
            if not Config.COHERE_API_KEY:
                raise Exception("Cohere API key is missing")
                
            # Initialize Pinecone client
            self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)
            
            # Get list of existing indexes
            indexes = self.pc.list_indexes()
            print(f"Existing indexes: {[idx['name'] for idx in indexes]}")
            
            # Clean index name - ensure it follows Pinecone's rules
            # Only lowercase letters, numbers and hyphens, max 45 chars
            safe_index_name = re.sub(r'[^a-z0-9-]', '-', index_name.lower())
            
            # Truncate if too long
            if len(safe_index_name) > 45:
                safe_index_name = safe_index_name[:45]
                
            print(f"Using safe index name: {safe_index_name}")
            
            # Check if index already exists
            index_exists = False
            for idx in indexes:
                if idx['name'] == safe_index_name:
                    index_exists = True
                    print(f"Index {safe_index_name} already exists")
                    break
            
            # Create new index if it doesn't exist
            if not index_exists:
                print(f"Creating new serverless index: {safe_index_name}")
                try:
                    # Create index with retry logic
                    for attempt in range(self.retry_attempts):
                        try:
                            self.pc.create_index(
                                name=safe_index_name,
                                dimension=Config.DIMENSION,
                                metric="cosine",
                                spec=ServerlessSpec(
                                    cloud=Config.PINECONE_CLOUD,
                                    region=Config.PINECONE_REGION
                                )
                            )
                            # Wait for index to be ready
                            time.sleep(5)
                            break
                        except Exception as e:
                            if attempt < self.retry_attempts - 1:
                                print(f"Attempt {attempt+1} failed, retrying: {str(e)}")
                                time.sleep(2)
                            else:
                                raise
                except Exception as e:
                    print(f"Error during index operations: {str(e)}")
                    raise Exception(f"Failed to create index: {str(e)}")
            
            # Connect to the index
            print(f"Connecting to index: {safe_index_name}")
            self.index = self.pc.Index(safe_index_name)
            self.active_index_name = safe_index_name
            
            # Get index stats to verify connection
            stats = self.index.describe_index_stats()
            print(f"Successfully connected to index. Stats: {stats}")
            
            # Initialize Cohere client
            self.co = cohere.Client(Config.COHERE_API_KEY)
            
            return True
            
        except Exception as e:
            print(f"Service initialization error: {str(e)}")
            raise

    def delete_index(self, index_name: str):
        try:
            existing_indexes = [index.name for index in self.pc.list_indexes()]
            if index_name in existing_indexes:
                print(f"Deleting index: {index_name}")
                self.pc.delete_index(index_name)
                print(f"Successfully deleted index: {index_name}")
        except Exception as e:
            print(f"Error deleting index: {str(e)}")
            raise Exception(f"Failed to delete index: {str(e)}")

class TextProcessor:
    @staticmethod
    def extract_text_from_pdf(file_bytes):
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            print(f"PDF extraction error: {str(e)}")
            return ""

    @staticmethod
    def extract_text_from_docx(file_bytes):
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            print(f"DOCX extraction error: {str(e)}")
            return ""

    @staticmethod
    def chunk_text(text, chunk_size=Config.CHUNK_SIZE):
        sentences = re.split(r'(?<=[.!?]) +', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += " " + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return [chunk for chunk in chunks if chunk.strip()]

class ChatbotManager:
    def __init__(self, file_path="data/chatbots.json"):
        self.chatbots = {}
        self.file_path = file_path
        self.service_manager = ServiceManager()
        self.base_dir = "data"
        
        # Ensure data directory exists
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Load existing chatbots if any
        self.load_chatbots()
    
    def load_chatbots(self):
        """Load chatbots from JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r') as f:
                    self.chatbots = json.load(f)
                print(f"Loaded {len(self.chatbots)} chatbots from {self.file_path}")
            else:
                # Create empty chatbots file
                self.save_chatbots()
                print(f"Created new chatbots file at {self.file_path}")
        except Exception as e:
            print(f"Error loading chatbots: {str(e)}")
            self.chatbots = {}
    
    def save_chatbots(self):
        """Save chatbots to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            with open(self.file_path, 'w') as f:
                json.dump(self.chatbots, f, indent=2)
            print(f"Saved {len(self.chatbots)} chatbots to {self.file_path}")
            return True
        except Exception as e:
            print(f"Error saving chatbots: {str(e)}")
            return False

    def create_chatbot(self, chatbot_name: str, user_id: str = None):
        print(f"Creating chatbot: {chatbot_name} for user: {user_id}")
        
        # Validate chatbot name
        if not re.match(r'^[a-zA-Z0-9-]+$', chatbot_name):
            raise ValueError("Chatbot name must only contain alphanumeric characters or hyphens")
        
        # Create a unique identifier
        timestamp = int(time.time())
        
        # Create a directory structure for the chatbot
        chatbot_id = f"{user_id}-{chatbot_name}" if user_id else chatbot_name
        
        # Check if chatbot with this ID already exists
        if chatbot_id in self.chatbots:
            raise ValueError(f"A chatbot with name '{chatbot_name}' already exists")
        
        # Ensure valid Pinecone index name - lowercase, no underscores, max 45 chars
        pinecone_index_name = f"rag-chatbot-{chatbot_id.lower().replace('_', '-')}-{timestamp}"
        
        # Trim index name if too long (Pinecone has a 45 character limit)
        if len(pinecone_index_name) > 45:
            # Keep timestamp and prefix, trim the middle part
            max_id_length = 45 - len(f"rag-chatbot--{timestamp}")
            trimmed_id = chatbot_id.lower().replace('_', '-')[:max_id_length]
            pinecone_index_name = f"rag-chatbot-{trimmed_id}-{timestamp}"
        
        print(f"Using Pinecone index name: {pinecone_index_name}")
        
        # Create data directories
        os.makedirs(f"data/{chatbot_id}", exist_ok=True)
        os.makedirs(f"data/{chatbot_id}/documents", exist_ok=True)
        os.makedirs(f"data/{chatbot_id}/chat_history", exist_ok=True)
        
        # Create an empty chat history file
        with open(f"data/{chatbot_id}/chat_history/history.json", 'w') as f:
            json.dump([], f)
        
        # Initialize services for this chatbot
        try:
            self.service_manager.initialize_services(pinecone_index_name)
        except Exception as e:
            print(f"Error initializing services: {str(e)}")
            # Clean up directories if initialization fails
            if os.path.exists(f"data/{chatbot_id}"):
                shutil.rmtree(f"data/{chatbot_id}")
            raise ValueError(f"Error initializing services: {str(e)}")
        
        # Add to chatbots dictionary
        self.chatbots[chatbot_id] = {
            "name": chatbot_name,
            "creation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": [],
            "index_name": pinecone_index_name,
            "user_id": user_id
        }
        
        # Save to file
        self.save_chatbots()
        
        return {
            "status": "success",
            "message": f"Chatbot '{chatbot_name}' created successfully",
            "chatbot_id": chatbot_id,
            "index_name": pinecone_index_name
        }
        
    def delete_chatbot(self, chatbot_id: str):
        """Delete a chatbot and its resources"""
        try:
            if chatbot_id not in self.chatbots:
                raise ValueError(f"Chatbot {chatbot_id} not found")
            
            # Get index name
            index_name = self.chatbots[chatbot_id].get("index_name")
            
            # Delete index if it exists
            if index_name:
                try:
                    self.service_manager.delete_index(index_name)
                except Exception as e:
                    print(f"Warning: Could not delete index {index_name}: {str(e)}")
            
            # Delete local files
            chatbot_dir = os.path.join(self.base_dir, chatbot_id)
            if os.path.exists(chatbot_dir):
                shutil.rmtree(chatbot_dir)
            
            # Remove from dictionary
            del self.chatbots[chatbot_id]
            
            # Save changes to file
            self.save_chatbots()
            
            return {"status": "success", "message": f"Chatbot {chatbot_id} deleted successfully"}
        except Exception as e:
            print(f"Error deleting chatbot: {str(e)}")
            raise ValueError(f"Failed to delete chatbot: {str(e)}")
            
    def add_file_to_chatbot(self, chatbot_id: str, filename: str):
        """Add a file reference to a chatbot"""
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
            
        if filename not in self.chatbots[chatbot_id]["files"]:
            self.chatbots[chatbot_id]["files"].append(filename)
            
        # Save changes to file
        self.save_chatbots()
        
        return True

    def get_user_chatbots(self, user_id: str) -> List[Dict]:
        """Get chatbots for a specific user"""
        user_chatbots = []
        
        try:
            for chatbot_id, chatbot_info in self.chatbots.items():
                if chatbot_info.get('user_id') == user_id:
                    # Ensure consistent date field name
                    creation_date = chatbot_info.get('creation_date') or chatbot_info.get('created_date', 'Unknown')
                    
                    user_chatbots.append({
                        'id': chatbot_id,
                        'name': chatbot_info.get('name', chatbot_id.split('-')[-1]),
                        'files': chatbot_info.get('files', []),
                        'date': creation_date
                    })
            return user_chatbots
        except Exception as e:
            print(f"Error getting user chatbots: {str(e)}")
            return []

    def get_all_chatbots(self) -> List[Dict]:
        """Get all chatbots (for admin)"""
        all_chatbots = []
        
        try:
            for chatbot_id, chatbot_info in self.chatbots.items():
                # Ensure consistent date field name
                creation_date = chatbot_info.get('creation_date') or chatbot_info.get('created_date', 'Unknown')
                
                all_chatbots.append({
                    'id': chatbot_id,
                    'name': chatbot_info.get('name', chatbot_id.split('-')[-1]),
                    'files': chatbot_info.get('files', []),
                    'date': creation_date,
                    'user_id': chatbot_info.get('user_id', 'Unknown')
                })
            return all_chatbots
        except Exception as e:
            print(f"Error getting all chatbots: {str(e)}")
            return []
            
    def get_chatbot_info(self, chatbot_id: str) -> Dict:
        """Get information about a specific chatbot"""
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
            
        chatbot_info = self.chatbots[chatbot_id]
        
        return {
            'id': chatbot_id,
            'name': chatbot_info.get('name', chatbot_id.split('-')[-1]),
            'files': chatbot_info.get('files', []),
            'date': chatbot_info.get('creation_date', 'Unknown'),
            'user_id': chatbot_info.get('user_id', 'Unknown'),
            'index_name': chatbot_info.get('index_name', 'Unknown')
        }
        
    def save_chat_history(self, chatbot_id: str, query: str, answer: str):
        """Save a chat interaction to the chatbot's history"""
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
            
        # Make sure the history directory exists
        history_dir = f"data/{chatbot_id}/chat_history"
        os.makedirs(history_dir, exist_ok=True)
        
        # Load existing history
        history_file = f"{history_dir}/history.json"
        history = []
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    history = json.load(f)
            except Exception as e:
                print(f"Error loading chat history: {str(e)}")
        
        # Add new interaction
        history.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": query,
            "answer": answer
        })
        
        # Save updated history
        try:
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving chat history: {str(e)}")
            return False
            
    def get_chat_history(self, chatbot_id: str) -> List[Dict]:
        """Get chat history for a specific chatbot"""
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
            
        history_file = f"data/{chatbot_id}/chat_history/history.json"
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading chat history: {str(e)}")
        
        return []

class UserManager:
    def __init__(self, file_path="data/users.json"):
        self.file_path = file_path
        self.users = {}
        self.load_users()
        
    def load_users(self):
        """Load users from JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r') as f:
                    self.users = json.load(f)
                print(f"Loaded {len(self.users)} users from {self.file_path}")
            else:
                # Create empty users file
                self.save_users()
                print(f"Created new users file at {self.file_path}")
        except Exception as e:
            print(f"Error loading users: {str(e)}")
            self.users = {}
    
    def save_users(self):
        """Save users to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            with open(self.file_path, 'w') as f:
                json.dump(self.users, f, indent=2)
            print(f"Saved {len(self.users)} users to {self.file_path}")
            return True
        except Exception as e:
            print(f"Error saving users: {str(e)}")
            return False
    
    def get_user(self, username):
        """Get user by username"""
        if username == HOST_USERNAME:
            return UserInDB(
                username=HOST_USERNAME,
                hashed_password=get_password_hash(HOST_PASSWORD),
                is_host=True,
                email="admin@example.com"
            )
        
        user_dict = self.users.get(username)
        if user_dict:
            return UserInDB(**user_dict)
        return None
    
    def create_user(self, user_data):
        """Create a new user"""
        if user_data.username in self.users:
            return False, "Username already exists"
            
        if user_data.username == HOST_USERNAME:
            return False, "Username not allowed"
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create user data (regular users only, host admin is hardcoded)
        user_dict = {
            "username": user_data.username,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "hashed_password": hashed_password,
            "disabled": False,
            "is_host": False  # All registered users are regular users
        }
        
        # Save to memory and file
        self.users[user_data.username] = user_dict
        if self.save_users():
            return True, "User created successfully"
        else:
            # Remove from memory if save failed
            del self.users[user_data.username]
            return False, "Failed to save user data"
    
    def authenticate_user(self, username, password):
        """Authenticate user with username and password"""
        # Special case for host admin
        if username == HOST_USERNAME and password == HOST_PASSWORD:
            return UserInDB(
                username=HOST_USERNAME,
                hashed_password=get_password_hash(HOST_PASSWORD),
                is_host=True,
                email="admin@example.com"
            )
        
        # Regular user authentication
        user = self.get_user(username)
        if not user:
            return False
        
        if not verify_password(password, user.hashed_password):
            return False
            
        return user
    
    def get_all_users(self):
        """Get list of all users (for admin)"""
        user_list = []
        for username, user_data in self.users.items():
            # Don't include password hash
            user_list.append({
                "username": username,
                "email": user_data.get("email"),
                "full_name": user_data.get("full_name"),
                "disabled": user_data.get("disabled", False),
                "is_host": user_data.get("is_host", False)
            })
        return user_list

# Initialize managers
Config.validate_env_vars()
chatbot_manager = ChatbotManager()
user_manager = UserManager()

# API Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return f.read()

@app.get("/chatbots")
async def list_chatbots(current_user: User = Depends(get_current_active_user)):
    try:
        if current_user.is_host or current_user.username == HOST_USERNAME:
            # Host admin can see all chatbots
            chatbots = chatbot_manager.get_all_chatbots()
        else:
            # Regular users can only see their chatbots
            chatbots = chatbot_manager.get_user_chatbots(current_user.username)
        
        return {"chatbots": chatbots}
    except Exception as e:
        print(f"Error listing chatbots: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list chatbots: {str(e)}"
        )

@app.post("/chatbot/create")
async def create_chatbot(request: Request, current_user: User = Depends(get_current_active_user)):
    try:
        data = await request.json()
        chatbot_name = data.get("name")
        
        if not chatbot_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chatbot name is required"
            )
            
        # Associate chatbot with user unless it's the host admin
        user_id = None if (current_user.is_host or current_user.username == HOST_USERNAME) else current_user.username
        
        try:
            result = chatbot_manager.create_chatbot(chatbot_name, user_id)
            
            # Format response to match what frontend expects
            return {
                "status": "success",
                "message": f"Chatbot '{chatbot_name}' created successfully",
                "chatbot_id": result["chatbot_id"],
                "name": chatbot_name
            }
        except ValueError as ve:
            # Handle validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve)
            )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error creating chatbot: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create chatbot: {str(e)}"
        )

@app.delete("/chatbot/{chatbot_id}")
async def delete_chatbot(chatbot_id: str, current_user: User = Depends(get_current_active_user)):
    try:
        # Check if chatbot exists
        if chatbot_id not in chatbot_manager.chatbots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chatbot {chatbot_id} not found"
            )
            
        # Check if user has access to this chatbot
        if not (current_user.is_host or current_user.username == HOST_USERNAME):
            # For regular users, check if the chatbot belongs to them
            chatbot_info = chatbot_manager.chatbots.get(chatbot_id)
            if not chatbot_info or chatbot_info.get("user_id") != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this chatbot"
                )
        
        # Delete the chatbot
        try:
            result = chatbot_manager.delete_chatbot(chatbot_id)
            return result
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve)
            )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error deleting chatbot: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete chatbot: {str(e)}"
        )

@app.post("/chatbot/{chatbot_id}/upload")
async def upload_file(chatbot_id: str, file: UploadFile = File(...), current_user: User = Depends(get_current_active_user)):
    try:
        # Check if chatbot exists
        if chatbot_id not in chatbot_manager.chatbots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chatbot {chatbot_id} not found"
            )
        
        # Check if user has access to this chatbot
        if not (current_user.is_host or current_user.username == HOST_USERNAME):
            chatbot_info = chatbot_manager.chatbots.get(chatbot_id)
            if not chatbot_info or chatbot_info.get("user_id") != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to upload to this chatbot"
                )
        
        # Validate file type
        filename = file.filename
        file_extension = os.path.splitext(filename)[1].lower()
        
        if file_extension not in ['.pdf', '.docx', '.txt']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF, DOCX, and TXT files are allowed"
            )
        
        # Create document directory if it doesn't exist
        documents_dir = f"data/{chatbot_id}/documents"
        os.makedirs(documents_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(documents_dir, filename)
        contents = await file.read()
        
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Process file content
        text = ""
        if file_extension == '.pdf':
            text = TextProcessor.extract_text_from_pdf(contents)
        elif file_extension == '.docx':
            text = TextProcessor.extract_text_from_docx(contents)
        elif file_extension == '.txt':
            text = contents.decode('utf-8')
        
        # Chunk text
        chunks = TextProcessor.chunk_text(text)
        
        # Get Pinecone index
        index_name = chatbot_manager.chatbots[chatbot_id]["index_name"]
        
        # Create embeddings and store in Pinecone
        try:
            # Initialize service manager if not already initialized
            service_manager = ServiceManager()
            service_manager.initialize_services(index_name)
            
            # Generate embeddings for chunks
            co_client = service_manager.co
            if not co_client:
                raise ValueError("Cohere client not initialized")
                
            embeddings_response = co_client.embed(
                texts=chunks,
                model='embed-english-v3.0',
                input_type='search_document'
            )
            
            # Get vectors from response
            vectors = embeddings_response.embeddings
            
            # Create metadata for chunks
            upsert_data = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                upsert_data.append({
                    'id': f"{filename}-{i}",
                    'values': vector,
                    'metadata': {
                        'text': chunk,
                        'source': filename,
                        'chunk_id': i
                    }
                })
            
            # Upsert to Pinecone
            service_manager.index.upsert(
                vectors=upsert_data
            )
            
            # Add file to chatbot
            chatbot_manager.add_file_to_chatbot(chatbot_id, filename)
            
            return {
                "status": "success",
                "message": f"File {filename} uploaded and processed successfully",
                "chunks": len(chunks)
            }
        except Exception as e:
            print(f"Error processing file: {str(e)}")
            
            # Cleanup the saved file if processing failed
            if os.path.exists(file_path):
                os.remove(file_path)
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file: {str(e)}"
            )
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )

@app.post("/chatbot/{chatbot_name}/ask")
async def chat_with_bot(chatbot_name: str, request: QueryRequest, current_user: User = Depends(get_current_active_user)):
    # Check if user has access to this chatbot
    if not (getattr(current_user, "is_host", False) or current_user.username == HOST_USERNAME):
        # For regular users, check if the chatbot belongs to them
        chatbot_info = chatbot_manager.chatbots.get(chatbot_name)
        if not chatbot_info or chatbot_info.get("user_id") != current_user.username:
            raise HTTPException(status_code=403, detail="You don't have permission to use this chatbot")

    if chatbot_name not in chatbot_manager.chatbots:
        raise HTTPException(404, "Chatbot not found")

    try:
        # Get the index name for this chatbot
        index_name = chatbot_manager.chatbots[chatbot_name]["index_name"]
        
        # Initialize service manager for this chatbot
        service_manager = ServiceManager()
        service_manager.initialize_services(index_name)
        
        # Get query embedding
        query_embedding = service_manager.co.embed(
            texts=[request.query],
            model='embed-english-v3.0',
            input_type="search_query"
        ).embeddings[0]

        # Search for similar vectors
        search_results = service_manager.index.query(
            vector=query_embedding,
            top_k=3,
            include_metadata=True
        )

        # Extract relevant contexts
        contexts = [match.metadata['text'] for match in search_results.matches]
        
        # Get chat history
        chat_history = chatbot_manager.get_chat_history(chatbot_name)
        # Get the last 3 conversations for context (reduced from 5)
        recent_history = chat_history[-3:] if len(chat_history) > 3 else chat_history
        
        # Prepare prompt with context and chat history
        system_prompt = """You are a helpful AI assistant. Using the provided context and chat history, 
        answer the user's question. If you cannot find the answer in the context, 
        say "I cannot find the answer in the provided context." 
        Base your answer on both the context and the conversation history provided."""

        # Format chat history for the prompt
        history_context = ""
        if recent_history:
            history_context = "\nPrevious conversation:\n"
            for entry in recent_history:
                history_context += f"User: {entry['query']}\nAssistant: {entry['answer']}\n"

        user_prompt = f"""Context: {' '.join(contexts)}
{history_context}

Current Question: {request.query}

Please provide a clear and concise answer based on both the context and conversation history above."""

        try:
            # Get response from selected model
            if request.model.lower() == "openai":
                if not OPENAI_API_KEY:
                    raise HTTPException(400, "OpenAI API key not configured")
                
                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500,
                    presence_penalty=0.1,  # Added to encourage more focused responses
                    frequency_penalty=0.1   # Added to reduce repetition
                )
                answer = response.choices[0].message.content

            elif request.model.lower() == "cohere":
                if not COHERE_API_KEY:
                    raise HTTPException(400, "Cohere API key not configured")
                
                combined_prompt = f"{system_prompt}\n\n{user_prompt}"

                response = service_manager.co.chat(
                    message=user_prompt,
                    model="command",
                    temperature=0.7,
                    chat_history=[],  # Cohere will use the history from the prompt
                    prompt_truncation='AUTO'
                )
                answer = response.text

            elif request.model.lower() == "togetherai":
                if not TOGETHERAI_API_KEY:
                    raise HTTPException(400, "TogetherAI API key not configured")
                
                url = "https://api.together.xyz/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {TOGETHERAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "mistralai/Mistral-7B-Instruct-v0.2",  # Changed from DeepSeek-R1 to avoid rate limit
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
                
                response = requests.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    raise HTTPException(500, f"TogetherAI API error: {response.text}")
                
                answer = response.json()["choices"][0]["message"]["content"]

            else:
                raise HTTPException(400, f"Unsupported model: {request.model}")

            # Save chat history
            chatbot_manager.save_chat_history(chatbot_name, request.query, answer)

            return JSONResponse(
                content={
                    "status": "success",
                    "response": answer,
                    "context_used": contexts,
                    "model_used": request.model
                }
            )

        except Exception as model_error:
            print(f"Error with {request.model} model: {str(model_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error generating response with {request.model}: {str(model_error)}"
            )

    except Exception as e:
        print(f"Error processing chat request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )

@app.get("/chatbot/{chatbot_id}/history")
async def get_chat_history(chatbot_id: str, current_user: User = Depends(get_current_active_user)):
    try:
        # Check if user has access to this chatbot
        if not (current_user.is_host or current_user.username == HOST_USERNAME):
            # For regular users, check if the chatbot belongs to them
            chatbot_info = chatbot_manager.chatbots.get(chatbot_id)
            if not chatbot_info or chatbot_info.get("user_id") != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this chatbot"
                )
        
        try:
            history = chatbot_manager.get_chat_history(chatbot_id)
            return {"history": history}
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(ve)
            )
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error getting chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chat history: {str(e)}"
        )

def test_pinecone_connection():
    try:
        pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        indexes = pc.list_indexes()
        print(f"Successfully connected to Pinecone. Available indexes: {[index.name for index in indexes]}")
        return True
    except Exception as e:
        print(f"Failed to connect to Pinecone: {str(e)}")
        return False

# Authentication Endpoints
@app.post("/register", response_model=User)
async def register_user(user_data: UserCreate):
    print(f"Registration attempt for username: {user_data.username}")
    
    # Validate username length
    if not user_data.username or len(user_data.username) < 3:
        print(f"Registration failed: Username too short ({len(user_data.username) if user_data.username else 0} chars)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters long"
        )
    
    # Validate password length    
    if not user_data.password or len(user_data.password) < 6:
        print(f"Registration failed: Password too short")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    
    try:
        success, message = user_manager.create_user(user_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
        
        print(f"User registered successfully: {user_data.username}")
        
        # Return user info without password
        return {
            "username": user_data.username,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "disabled": False,
            "is_host": False  # All registered users are regular users
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    print(f"Login attempt for username: {form_data.username}")
    
    try:
        # Validate credentials
        user = authenticate_user(form_data.username, form_data.password)
        if not user:
            print(f"Login failed: Invalid credentials for user {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create token data with is_host flag
        is_host = getattr(user, "is_host", False) or user.username == HOST_USERNAME
        token_data = {
            "sub": user.username,
            "is_host": is_host
        }
        
        # Generate token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data=token_data, expires_delta=access_token_expires
        )
        
        print(f"Login successful: {user.username} (is_host: {is_host})")
        print(f"Generated token with expiry: {access_token_expires}")
        print(f"Token first 20 chars: {access_token[:20]}...")
        
        # Return token information
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

if __name__ == "__main__":
    try:
        # Validate environment and create necessary directories
        print("starting server")
        Config.validate_env_vars()
        
        # Test Pinecone connection
        if not test_pinecone_connection():
            print("Failed to establish Pinecone connection. Please check your configuration.")
            sys.exit(1)
            
        os.makedirs("uploaded_files", exist_ok=True)
        os.makedirs("chat_history", exist_ok=True)
        
        # Start the application
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        print(f"Failed to start application: {str(e)}")