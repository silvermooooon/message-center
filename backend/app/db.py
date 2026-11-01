import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


url = os.environ.get("DATABASE_URL", "postgresql+psycopg://localhost/twinteams")
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if not url.startswith("postgresql+psycopg://"):
    raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
engine = create_engine(url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
