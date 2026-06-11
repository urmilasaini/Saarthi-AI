"""MongoDB client singleton. Lazy-initialised so tests without a real URI never fail on import."""

import logging
from pymongo import MongoClient
from app import config

logger = logging.getLogger("saarthi.db")

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = config.mongodb_uri()
        if not uri:
            raise RuntimeError("MONGODB_URI is not set — add it to .env")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    return get_client()["saarthi"]
