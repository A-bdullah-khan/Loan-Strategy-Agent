"""MongoDB connection for persistent chat history (see mcp_server.chat_history).

pymongo's MongoClient already pools connections internally, so the process
keeps a single cached client rather than reconnecting per request.
"""

from functools import lru_cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError

DEFAULT_DB_NAME = "loan_agent_db"


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    return MongoClient(settings.MONGO_URI)


def get_mongo_db() -> Database:
    """Returns the database named in MONGO_URI's path, falling back to
    DEFAULT_DB_NAME if the URI doesn't specify one (e.g. a bare Atlas URI)."""
    client = get_mongo_client()
    try:
        return client.get_default_database()
    except ConfigurationError:
        return client[DEFAULT_DB_NAME]
