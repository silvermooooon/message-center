"""Create the Message Center tables in the configured PostgreSQL schema."""

from . import models  # noqa: F401
from .db import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
