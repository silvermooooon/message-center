"""Regenerate the reference PostgreSQL DDL from the SQLAlchemy models."""

from pathlib import Path

from sqlalchemy import create_mock_engine

from app import models  # noqa: F401
from app.db import Base

statements = []
engine = create_mock_engine(
    "postgresql+psycopg://",
    lambda statement, *args, **kwargs: statements.append(
        "\n".join(
            line.rstrip()
            for line in str(statement.compile(dialect=engine.dialect)).strip().splitlines()
        )
        + ";"
    ),
)
Base.metadata.create_all(engine)
Path(__file__).resolve().parents[2].joinpath("schema.sql").write_text(
    "-- Generated from backend/app/models.py via SQLAlchemy metadata.\n\n"
    + "\n\n".join(statements)
    + "\n"
)
