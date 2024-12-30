from typing import Any, Dict, Optional

from pymongo import MongoClient
from pymongo.collection import Collection

from chat.core.config import settings


class MongoDBConnection:
    """MongoDB Connection and Collection Manager"""

    def __init__(self, uri: Optional[str] = None):
        self.client: Optional[MongoClient] = None
        self.db: Optional[Any] = None
        self.collections: Dict[str, Collection] = {}

        self.uri = uri or settings.MONGO_DB_URI

    def connect(self) -> Dict[str, Collection]:
        """Establish the connection and initialize collections."""
        self.client = MongoClient(self.uri, appname="chequebase-ai-rag")
        self.client.start_session()  # Ensures connection is asynchronous
        self.db = self.client[settings.MONGO_DB_NAME]

        # Initialize the required collection (context)
        walletentries_collection = self.db[
            settings.MONGO_DB_WALLETENTRIES_COLLECTION_NAME
        ]
        budgets_collection = self.db[settings.MONGO_DB_BUDGETS_COLLECTION_NAME]
        users_collection = self.db[settings.MONGO_DB_USERS_COLLECTION_NAME]

        self.collections["walletentries"] = walletentries_collection
        self.collections["budgets"] = budgets_collection
        self.collections["users"] = users_collection

        return self.collections

    def close(self):
        """Closes the MongoDB client connection."""
        if self.client:
            self.client.close()


mongodb_connection = MongoDBConnection(settings.MONGO_DB_URI)
collections = mongodb_connection.connect()

# Asynchronous database connection usage
def connect_to_database():
    try:
        return mongodb_connection.connect()
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        raise
