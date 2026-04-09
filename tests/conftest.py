import pytest
from slackwrap.db import Database


@pytest.fixture
def db():
    """In-memory database for testing."""
    database = Database(":memory:", check_same_thread=False)
    database.initialize()
    yield database
    database.close()
