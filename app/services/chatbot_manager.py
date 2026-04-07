import os
import re
import json
import time
import shutil
from datetime import datetime
from typing import List, Dict

from app.config import Config
from app.services.service_manager import ServiceManager, invalidate_service_cache


class ChatbotManager:
    def __init__(self, file_path="data/chatbots.json"):
        self.chatbots = {}
        self.file_path = file_path
        self.service_manager = ServiceManager()
        self.base_dir = "data"

        os.makedirs(self.base_dir, exist_ok=True)
        self.load_chatbots()

    def load_chatbots(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            if os.path.exists(self.file_path):
                with open(self.file_path, "r") as f:
                    self.chatbots = json.load(f)
                print(f"Loaded {len(self.chatbots)} chatbots from {self.file_path}")
            else:
                self.save_chatbots()
        except Exception as e:
            print(f"Error loading chatbots: {str(e)}")
            self.chatbots = {}

    def save_chatbots(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump(self.chatbots, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving chatbots: {str(e)}")
            return False

    def create_chatbot(
        self, chatbot_name: str, user_id: str = None, is_public: bool = False
    ):
        if not re.match(r"^[a-zA-Z0-9-]+$", chatbot_name):
            raise ValueError(
                "Chatbot name must only contain alphanumeric characters or hyphens"
            )

        timestamp = int(time.time())
        chatbot_id = f"{user_id}-{chatbot_name}" if user_id else chatbot_name

        if chatbot_id in self.chatbots:
            raise ValueError(f"A chatbot with name '{chatbot_name}' already exists")

        pinecone_index_name = (
            f"rag-chatbot-{chatbot_id.lower().replace('_', '-')}-{timestamp}"
        )
        if len(pinecone_index_name) > 45:
            max_id_length = 45 - len(f"rag-chatbot--{timestamp}")
            trimmed_id = chatbot_id.lower().replace("_", "-")[:max_id_length]
            pinecone_index_name = f"rag-chatbot-{trimmed_id}-{timestamp}"

        os.makedirs(f"data/{chatbot_id}", exist_ok=True)
        os.makedirs(f"data/{chatbot_id}/documents", exist_ok=True)
        os.makedirs(f"data/{chatbot_id}/chat_history", exist_ok=True)

        with open(f"data/{chatbot_id}/chat_history/history.json", "w") as f:
            json.dump([], f)

        try:
            self.service_manager.initialize_services(pinecone_index_name)
        except Exception as e:
            if os.path.exists(f"data/{chatbot_id}"):
                shutil.rmtree(f"data/{chatbot_id}")
            raise ValueError(f"Error initializing services: {str(e)}")

        self.chatbots[chatbot_id] = {
            "name": chatbot_name,
            "creation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": [],
            "index_name": pinecone_index_name,
            "user_id": user_id,
            "is_public": is_public,
        }
        self.save_chatbots()

        return {
            "status": "success",
            "message": f"Chatbot '{chatbot_name}' created successfully",
            "chatbot_id": chatbot_id,
            "index_name": pinecone_index_name,
        }

    def delete_chatbot(self, chatbot_id: str):
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")

        index_name = self.chatbots[chatbot_id].get("index_name")
        if index_name:
            try:
                self.service_manager.delete_index(index_name)
                invalidate_service_cache(index_name)
            except Exception as e:
                print(f"Warning: Could not delete index {index_name}: {str(e)}")

        chatbot_dir = os.path.join(self.base_dir, chatbot_id)
        if os.path.exists(chatbot_dir):
            shutil.rmtree(chatbot_dir)

        del self.chatbots[chatbot_id]
        self.save_chatbots()

        return {
            "status": "success",
            "message": f"Chatbot {chatbot_id} deleted successfully",
        }

    def add_file_to_chatbot(self, chatbot_id: str, filename: str):
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
        if filename not in self.chatbots[chatbot_id]["files"]:
            self.chatbots[chatbot_id]["files"].append(filename)
        self.save_chatbots()
        return True

    def get_user_chatbots(self, user_id: str) -> List[Dict]:
        user_chatbots = []
        for chatbot_id, chatbot_info in self.chatbots.items():
            if chatbot_info.get("user_id") == user_id:
                creation_date = chatbot_info.get(
                    "creation_date", chatbot_info.get("created_date", "Unknown")
                )
                user_chatbots.append(
                    {
                        "id": chatbot_id,
                        "name": chatbot_info.get(
                            "name", chatbot_id.split("-")[-1]
                        ),
                        "files": chatbot_info.get("files", []),
                        "date": creation_date,
                    }
                )
        return user_chatbots

    def get_all_chatbots(self) -> List[Dict]:
        all_chatbots = []
        for chatbot_id, chatbot_info in self.chatbots.items():
            creation_date = chatbot_info.get(
                "creation_date", chatbot_info.get("created_date", "Unknown")
            )
            all_chatbots.append(
                {
                    "id": chatbot_id,
                    "name": chatbot_info.get("name", chatbot_id.split("-")[-1]),
                    "files": chatbot_info.get("files", []),
                    "date": creation_date,
                    "user_id": chatbot_info.get("user_id", "Unknown"),
                }
            )
        return all_chatbots

    def get_chatbot_info(self, chatbot_id: str) -> Dict:
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")
        info = self.chatbots[chatbot_id]
        return {
            "id": chatbot_id,
            "name": info.get("name", chatbot_id.split("-")[-1]),
            "files": info.get("files", []),
            "date": info.get("creation_date", "Unknown"),
            "user_id": info.get("user_id", "Unknown"),
            "index_name": info.get("index_name", "Unknown"),
        }

    def save_chat_history(self, chatbot_id: str, query: str, answer: str):
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")

        history_dir = f"data/{chatbot_id}/chat_history"
        os.makedirs(history_dir, exist_ok=True)

        history_file = f"{history_dir}/history.json"
        history = []

        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                pass

        history.append(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": query,
                "answer": answer,
            }
        )

        try:
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving chat history: {str(e)}")
            return False

    def get_chat_history(self, chatbot_id: str) -> List[Dict]:
        if chatbot_id not in self.chatbots:
            raise ValueError(f"Chatbot {chatbot_id} not found")

        history_file = f"data/{chatbot_id}/chat_history/history.json"
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def get_public_chatbots(self) -> List[Dict]:
        public_chatbots = []
        for chatbot_id, chatbot_info in self.chatbots.items():
            if chatbot_info.get("is_public", False):
                creation_date = chatbot_info.get(
                    "creation_date", chatbot_info.get("created_date", "Unknown")
                )
                public_chatbots.append(
                    {
                        "id": chatbot_id,
                        "name": chatbot_info.get(
                            "name", chatbot_id.split("-")[-1]
                        ),
                        "files": chatbot_info.get("files", []),
                        "date": creation_date,
                        "user_id": chatbot_info.get("user_id", "Unknown"),
                    }
                )
        return public_chatbots
