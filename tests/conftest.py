import pytest
from slackwrap.db import Database


@pytest.fixture
def db():
    """In-memory database for testing."""
    database = Database(":memory:")
    database.initialize()
    yield database
    database.close()
