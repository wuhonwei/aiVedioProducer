import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aivp.db import Base
from aivp.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'t.db'}")


@pytest.fixture
def db_session(settings: Settings):
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
