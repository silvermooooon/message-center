import atexit
import os
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

base_url = os.environ.get("MESSAGE_CENTER_TEST_DB_URL")
if not base_url:
    raise RuntimeError("Set MESSAGE_CENTER_TEST_DB_URL for isolated PostgreSQL tests")
base_url = base_url.replace("postgresql+psycopg://", "postgresql://")
schema = "mc_test_" + uuid4().hex
with psycopg.connect(base_url, autocommit=True) as connection:
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))


def cleanup():
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


atexit.register(cleanup)
parsed = urlsplit(base_url)
query = dict(parse_qsl(parsed.query))
query["options"] = f"-c search_path={schema}"
os.environ["DATABASE_URL"] = urlunsplit(parsed._replace(query=urlencode(query, quote_via=quote)))
os.environ["MESSAGE_CENTER_SERVICE_TOKEN"] = "test-token"
os.environ["DUET_BASE_URL"] = "http://duet.test"
os.environ.pop("REDIS_URL", None)
