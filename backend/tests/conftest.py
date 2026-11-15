import os
os.environ.setdefault('JWT_SECRET','test-secret')
os.environ.setdefault('REDIS_URL','redis://localhost:6379/15')
os.environ.setdefault('SEED_DEMO','false')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.config import database
from src.config.database import Base
import src.models  # noqa: F401 注册全部ORM模型

_test_engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
database.engine=_test_engine
database.SessionLocal=sessionmaker(bind=_test_engine,expire_on_commit=False)
Base.metadata.create_all(_test_engine)

import pytest

@pytest.fixture
def db():
 Base.metadata.drop_all(_test_engine);Base.metadata.create_all(_test_engine)
 session=database.SessionLocal()
 try:yield session
 finally:session.close()

@pytest.fixture
def actor():
 return 'analyst@lingdu.demo'
