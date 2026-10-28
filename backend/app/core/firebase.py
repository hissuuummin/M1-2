import json
import logging
import os
from typing import Any, Dict, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore
from app.core.config import settings

logger = logging.getLogger("investment_mirror.firebase")

_firestore_client = None
_is_mock = False


class MockDocumentReference:
    def __init__(self, collection: "MockCollectionReference", doc_id: str):
        self.collection = collection
        self.id = doc_id

    def get(self) -> "MockDocumentSnapshot":
        data = self.collection.data_store.get(self.id)
        return MockDocumentSnapshot(self.id, data)

    def set(self, data: Dict[str, Any], merge: bool = False):
        if merge and self.id in self.collection.data_store:
            self.collection.data_store[self.id].update(data)
        else:
            self.collection.data_store[self.id] = dict(data)
        self.collection.save()

    def update(self, data: Dict[str, Any]):
        if self.id not in self.collection.data_store:
            raise Exception(f"Document {self.id} does not exist")
        self.collection.data_store[self.id].update(data)
        self.collection.save()

    def delete(self):
        if self.id in self.collection.data_store:
            del self.collection.data_store[self.id]
            self.collection.save()


class MockDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class MockQuery:
    def __init__(self, collection: "MockCollectionReference", filters=None, order_field=None, direction="asc", limit_val=None):
        self.collection = collection
        self.filters = filters or []
        self.order_field = order_field
        self.direction = direction
        self.limit_val = limit_val

    def order_by(self, field: str, direction: str = "ASCENDING") -> "MockQuery":
        dir_str = "desc" if "DESC" in str(direction).upper() else "asc"
        return MockQuery(self.collection, self.filters, field, dir_str, self.limit_val)

    def limit(self, val: int) -> "MockQuery":
        return MockQuery(self.collection, self.filters, self.order_field, self.direction, val)

    def stream(self):
        items = [
            MockDocumentSnapshot(doc_id, data)
            for doc_id, data in self.collection.data_store.items()
        ]
        if self.order_field:
            def sort_key(doc):
                val = (doc.to_dict() or {}).get(self.order_field)
                return (val is None, val)
            items.sort(key=sort_key, reverse=(self.direction == "desc"))
        if self.limit_val is not None:
            items = items[:self.limit_val]
        for it in items:
            yield it


class MockCollectionReference:
    def __init__(self, name: str, root_dir: str = ".local_db"):
        self.name = name
        self.root_dir = root_dir
        self.file_path = os.path.join(self.root_dir, f"{name}.json")
        self.data_store: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data_store = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load mock collection {self.name}: {e}")
                self.data_store = {}

    def save(self):
        try:
            os.makedirs(self.root_dir, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data_store, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save mock collection {self.name}: {e}")

    def document(self, doc_id: Optional[str] = None) -> MockDocumentReference:
        if not doc_id:
            import uuid
            doc_id = uuid.uuid4().hex[:20]
        return MockDocumentReference(self, doc_id)

    def order_by(self, field: str, direction: str = "ASCENDING") -> MockQuery:
        return MockQuery(self).order_by(field, direction)

    def limit(self, val: int) -> MockQuery:
        return MockQuery(self).limit(val)

    def stream(self):
        return MockQuery(self).stream()


class MockFirestoreClient:
    def __init__(self, root_dir: str = ".local_db"):
        self.root_dir = root_dir
        self._collections: Dict[str, MockCollectionReference] = {}

    def collection(self, name: str) -> MockCollectionReference:
        if name not in self._collections:
            self._collections[name] = MockCollectionReference(name, self.root_dir)
        return self._collections[name]


def get_firestore_client():
    global _firestore_client, _is_mock
    if _firestore_client is not None:
        return _firestore_client

    # Check for real Firebase credentials
    cred = None
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            cert_data = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            cred = credentials.Certificate(cert_data)
            logger.info("Loaded Firebase credentials from FIREBASE_SERVICE_ACCOUNT_JSON")
        except Exception as e:
            logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
    elif settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        try:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            logger.info(f"Loaded Firebase credentials from file: {settings.FIREBASE_CREDENTIALS_PATH}")
        except Exception as e:
            logger.error(f"Failed to parse credentials file: {e}")

    if cred is not None:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            _firestore_client = firestore.client()
            _is_mock = False
            logger.info("Firestore client initialized successfully with real Firebase")
            return _firestore_client
        except Exception as e:
            logger.error(f"Error initializing Firebase Firestore: {e}")

    # Fallback to local persistent JSON mock
    logger.info("Initializing Local Firestore Store (Persistent JSON for local dev/testing)")
    _firestore_client = MockFirestoreClient()
    _is_mock = True
    return _firestore_client


def is_mock_firestore() -> bool:
    global _is_mock
    return _is_mock
