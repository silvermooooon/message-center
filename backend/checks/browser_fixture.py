"""Launch an isolated, disposable browser acceptance fixture."""

import os
import subprocess
import sys
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

base = os.environ["MESSAGE_CENTER_TEST_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
schema = "mc_test_" + uuid4().hex
with psycopg.connect(base, autocommit=True) as connection:
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
parsed = urlsplit(base)
query = dict(parse_qsl(parsed.query))
query["options"] = f"-c search_path={schema}"
env = {
    **os.environ,
    "DATABASE_URL": urlunsplit(parsed._replace(query=urlencode(query, quote_via=quote))),
    "MESSAGE_CENTER_TEST_FIXTURE": "true",
    "MESSAGE_CENTER_SERVICE_TOKEN": "fixture-token",
    "MESSAGE_CENTER_ENRICHMENT_ENABLED": "false",
}
try:
    subprocess.run([sys.executable, "-m", "app.init_db"], env=env, check=True)
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8021"],
        env=env,
        check=False,
    )
finally:
    with psycopg.connect(base, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
