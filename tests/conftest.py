"""Shared fixtures: a throw-away database, a temp output folder, a test client.

The app's real dependencies (database session, generation service) are replaced
with test versions using FastAPI's dependency_overrides.
"""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_generation_service
from app.core.config import get_settings
from app.db.database import Base, create_db_engine, create_session_factory
from app.main import app
from app.services.generation_service import GenerationService
from app.services.pdf_service import CertificateRenderer


@pytest.fixture()
def session_factory(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def output_dir(tmp_path):
    return tmp_path / "generated"


@pytest.fixture()
def real_renderer():
    return CertificateRenderer(get_settings().template_path)


@pytest.fixture()
def client_factory(session_factory, output_dir, real_renderer):
    """Returns a function that builds a client using the renderer you choose."""

    def build(renderer=None) -> TestClient:
        service = GenerationService(session_factory, renderer or real_renderer, output_dir)

        def override_get_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_generation_service] = lambda: service
        return TestClient(app)

    yield build
    app.dependency_overrides.clear()


@pytest.fixture()
def client(client_factory):
    """Client with the real PDF renderer."""
    return client_factory()
