import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock
from silex_engine.storage.database import Database
from silex_engine.memory.memory_store import MemoryStore
from silex_engine.world.graph import KnowledgeGraph

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def db():
    """In-memory SQLite database for testing."""
    _db = Database(":memory:")
    await _db.connect()
    yield _db
    await _db.close()

@pytest_asyncio.fixture
async def memory_store(db):
    """MemoryStore with mocked VectorStore."""
    store = MemoryStore(db)
    # Mock VectorStore to avoid needing ChromaDB running
    store.vs = MagicMock()
    store.vs.is_active = True
    store.vs.add_chunks = MagicMock()
    store.vs.search = MagicMock(return_value=[])
    store.vs.delete_by_ids = MagicMock()
    
    # Mock A-MAC and Guard to admit everything during isolated tests
    store.amac = MagicMock()
    store.amac.evaluate_admission = AsyncMock(return_value={
        "admitted": True,
        "composite_score": 0.9,
        "utility": 0.9,
        "confidence": 0.9,
        "novelty": 0.9,
        "recency": 0.9,
        "type_prior": 0.9
    })
    
    store.guard = MagicMock()
    store.guard.validate_write_attempt = MagicMock(return_value={
        "allowed": True,
        "flagged": False,
        "signature": "test_sig"
    })
    
    yield store

@pytest_asyncio.fixture
async def knowledge_graph(db):
    """KnowledgeGraph fixture."""
    kg = KnowledgeGraph(db)
    yield kg
