import os
import json

from app.config import Config
from app.models.schemas import UserInDB


class UserManager:
    def __init__(self, file_path="data/users.json"):
        self.file_path = file_path
        self.users = {}
        self._pwd_context = None
        self.load_users()

    @property
    def pwd_context(self):
        if self._pwd_context is None:
            from app.auth import pwd_context

            self._pwd_context = pwd_context
        return self._pwd_context

    def load_users(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            if os.path.exists(self.file_path):
                with open(self.file_path, "r") as f:
                    self.users = json.load(f)
                print(f"Loaded {len(self.users)} users from {self.file_path}")
            else:
                self.save_users()
        except Exception as e:
            print(f"Error loading users: {str(e)}")
            self.users = {}

    def save_users(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump(self.users, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving users: {str(e)}")
            return False

    def get_user(self, username):
        if username == Config.HOST_USERNAME:
            return UserInDB(
                username=Config.HOST_USERNAME,
                hashed_password=self.pwd_context.hash("__placeholder__"),
                is_host=True,
                email="admin@example.com",
            )

        user_dict = self.users.get(username)
        if user_dict:
            return UserInDB(**user_dict)
        return None

    def create_user(self, user_data):
        if user_data.username in self.users:
            return False, "Username already exists"
        if user_data.username == Config.HOST_USERNAME:
            return False, "Username not allowed"

        hashed_password = self.pwd_context.hash(user_data.password)

        user_dict = {
            "username": user_data.username,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "hashed_password": hashed_password,
            "disabled": False,
            "is_host": False,
        }

        self.users[user_data.username] = user_dict
        if self.save_users():
            return True, "User created successfully"
        else:
            del self.users[user_data.username]
            return False, "Failed to save user data"

    def authenticate_user(self, username, password):
        if username == Config.HOST_USERNAME and password == Config.HOST_PASSWORD:
            return UserInDB(
                username=Config.HOST_USERNAME,
                hashed_password=self.pwd_context.hash("__placeholder__"),
                is_host=True,
                email="admin@example.com",
            )

        user = self.get_user(username)
        if not user:
            return False
        if not self.pwd_context.verify(password, user.hashed_password):
            return False
        return user

    def get_all_users(self):
        user_list = []
        for username, user_data in self.users.items():
            user_list.append(
                {
                    "username": username,
                    "email": user_data.get("email"),
                    "full_name": user_data.get("full_name"),
                    "disabled": user_data.get("disabled", False),
                    "is_host": user_data.get("is_host", False),
                }
            )
        return user_list
