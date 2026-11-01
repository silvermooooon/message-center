# Message Center

A local demo for publishing structured announcements and delivering them to Duet owners. The canonical message is stored once in PostgreSQL; each recipient has a separate durable receipt. Sources can publish by webhook, HTTP JSON polling, or manual entry. Messages support revisions, withdrawal, expiry, topic/channel subscriptions, feedback, and delivery diagnostics.

**Demo identity:** log in as `DEV-AAA` (Alex), `DEV-BBB` (Maya), or `DEV-CCC` (Jordan). All three signed-in users can browse and manage all demo data. There is no role system or permission isolation in this version. Authentication is separate from the deliberately permissive authorization seam. Do not expose this development login to an untrusted network.

## Run locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), PostgreSQL, Redis (optional wake hints), Node 22.12+, and the sibling `agent-runtime` checkout for optional enrichment. PostgreSQL may be the same database as Duet; this application creates only `mc_*` tables. Use a PostgreSQL database where you are authorized to create tables.

```sh
cd frontend
npm ci
npm run build
cd ../backend
cp .env.example .env
# Edit .env locally: DATABASE_URL, DUET_BASE_URL, and a shared
# MESSAGE_CENTER_SERVICE_TOKEN configured identically on Duet.
uv sync
uv run python run_local.py
```

Open <http://127.0.0.1:8020>. The launcher explicitly initializes the tables, then runs one API process and one worker; terminate it with Ctrl-C. Build the frontend before starting the API, which serves `frontend/dist` on the same origin. Alternatively initialize once with `uv run python -m app.init_db`, then run `uv run uvicorn app.main:app --host 127.0.0.1 --port 8020` and exactly one `uv run python -m app.worker` with the same environment. `.env` is read by the launcher; export the variables when starting processes separately. `schema.sql` is a reference generated from SQLAlchemy metadata; do not apply it over existing tables. Regenerate it with `uv run python -m checks.generate_schema` after changing the models.

A shared `MESSAGE_CENTER_SERVICE_TOKEN` authenticates service traffic; webhook source tokens are separate, write-only credentials. Set real values only in the ignored local `.env`. The API contract, source schema, and callback details are in [docs/api-contract.md](docs/api-contract.md).

## Delivery and data semantics

Explicit recipients take precedence over matching subscriptions; otherwise all enabled matching channel/topic subscriptions fan out, with immediate taking precedence over digest for the same owner. Both modes are durably delivered to Duet: immediate admits a Duet request; digest is recorded for its later system review without an immediate LLM wake. A stable delivery ID makes callback retries safe. The worker retries failures at bounded intervals, then marks them failed for a manual retry. PostgreSQL is authoritative; Redis publishes disposable wake hints, and a 30–60 second reconciliation interval plus indexed retry, polling, and expiry deadlines recovers missed hints. Run a single Message Center worker.

Updating content creates a new version and fanout; withdrawal, expiry, and newer versions cancel outstanding old receipts. Already processed results are retained as history. `accepted` means Duet accepted a receipt, `processed` means Duet reported consumption, and `notified=true` means an owner update was confirmed; `false` means it was not confirmed and is not evidence that the owner has not seen it. Digest reporting cannot attribute an owner update to an individual receipt in this first version. None of these states implies a human read the message. A separate explicit human-read field and structured acknowledge/attending/declined feedback are independent. Message contents are reference data and do not authorize actions.

## Optional enrichment

Enrichment is disabled by default and never required for publication or delivery. To enable it, install `uv sync --extra enrichment`, configure the sibling Agent Runtime's OpenAI provider environment, and set `MESSAGE_CENTER_ENRICHMENT_ENABLED=true` for the API process. The explicit action calls only `gpt-6-luna`, with no tools, and stores a bounded classification and summary separately from the original content. A failed call leaves the original message intact. Enabling it may incur provider charges; tests do not call a live provider.

## Tests

```sh
cd backend
MESSAGE_CENTER_TEST_DB_URL='postgresql://...' uv run pytest -q
```

Tests create and drop a uniquely named isolated PostgreSQL schema and never reset the application tables. For a disposable browser fixture, set the same variable and run `uv run python checks/browser_fixture.py`; it serves port 8021 with `/health` reporting `acceptance_fixture: true`. Stop it normally to remove its test schema. No real Duet, provider, or worker is connected to that fixture.
