import re
import time
import cohere
from pinecone import Pinecone, ServerlessSpec

from app.config import Config


class ServiceManager:
    def __init__(self):
        self.co = None
        self.pc = None
        self.index = None
        self.active_index_name = None
        self.retry_attempts = 3

    def initialize_services(self, index_name: str):
        if not Config.PINECONE_API_KEY:
            raise Exception("Pinecone API key is missing")
        if not Config.COHERE_API_KEY:
            raise Exception("Cohere API key is missing")

        self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)

        indexes = self.pc.list_indexes()
        safe_index_name = re.sub(r"[^a-z0-9-]", "-", index_name.lower())
        if len(safe_index_name) > 45:
            safe_index_name = safe_index_name[:45]

        index_exists = any(idx["name"] == safe_index_name for idx in indexes)

        if not index_exists:
            for attempt in range(self.retry_attempts):
                try:
                    self.pc.create_index(
                        name=safe_index_name,
                        dimension=Config.DIMENSION,
                        metric="cosine",
                        spec=ServerlessSpec(
                            cloud=Config.PINECONE_CLOUD,
                            region=Config.PINECONE_REGION,
                        ),
                    )
                    time.sleep(5)
                    break
                except Exception as e:
                    if attempt < self.retry_attempts - 1:
                        print(f"Attempt {attempt+1} failed, retrying: {str(e)}")
                        time.sleep(2)
                    else:
                        raise Exception(f"Failed to create index: {str(e)}")

        self.index = self.pc.Index(safe_index_name)
        self.active_index_name = safe_index_name

        stats = self.index.describe_index_stats()
        print(f"Connected to index {safe_index_name}. Stats: {stats}")

        self.co = cohere.Client(Config.COHERE_API_KEY)
        return True

    def delete_index(self, index_name: str):
        existing_indexes = [index.name for index in self.pc.list_indexes()]
        if index_name in existing_indexes:
            self.pc.delete_index(index_name)
            print(f"Deleted index: {index_name}")


# Cache of initialized ServiceManager instances per index name
_service_cache: dict[str, ServiceManager] = {}


def get_service_manager(index_name: str) -> ServiceManager:
    if index_name in _service_cache:
        return _service_cache[index_name]

    sm = ServiceManager()
    sm.initialize_services(index_name)
    _service_cache[index_name] = sm
    return sm


def invalidate_service_cache(index_name: str):
    _service_cache.pop(index_name, None)
