-- Generated from backend/app/models.py via SQLAlchemy metadata.

CREATE TABLE mc_sessions (
	token_hash VARCHAR(64) NOT NULL,
	owner_id VARCHAR(100) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash)
);

CREATE TABLE mc_sources (
	id VARCHAR(32) NOT NULL,
	name VARCHAR(200) NOT NULL,
	type VARCHAR(20) NOT NULL,
	enabled BOOLEAN NOT NULL,
	url TEXT,
	token TEXT,
	poll_interval_seconds INTEGER NOT NULL,
	next_poll_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_error TEXT,
	PRIMARY KEY (id)
);

CREATE INDEX ix_mc_sources_next_poll_at ON mc_sources (next_poll_at);

CREATE TABLE mc_subscriptions (
	id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(100) NOT NULL,
	channel VARCHAR(200),
	topic VARCHAR(200),
	mode VARCHAR(20) NOT NULL,
	enabled BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_mc_subscriptions_owner_id ON mc_subscriptions (owner_id);

CREATE TABLE mc_messages (
	id VARCHAR(32) NOT NULL,
	source_id VARCHAR(32),
	external_id VARCHAR(200),
	client_request_key VARCHAR(200),
	title VARCHAR(500) NOT NULL,
	body TEXT NOT NULL,
	kind VARCHAR(80) NOT NULL,
	publisher VARCHAR(200),
	topic VARCHAR(200),
	channel VARCHAR(200),
	recipients JSONB NOT NULL,
	metadata JSONB NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE,
	enrichment JSONB,
	PRIMARY KEY (id),
	UNIQUE (source_id, external_id),
	UNIQUE (client_request_key),
	FOREIGN KEY(source_id) REFERENCES mc_sources (id)
);

CREATE INDEX mc_message_expiry ON mc_messages (status, expires_at);

CREATE TABLE mc_revisions (
	id VARCHAR(32) NOT NULL,
	message_id VARCHAR(32) NOT NULL,
	version INTEGER NOT NULL,
	content JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (message_id, version),
	FOREIGN KEY(message_id) REFERENCES mc_messages (id)
);

CREATE TABLE mc_deliveries (
	id VARCHAR(32) NOT NULL,
	message_id VARCHAR(32) NOT NULL,
	version INTEGER NOT NULL,
	owner_id VARCHAR(100) NOT NULL,
	mode VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	notified BOOLEAN NOT NULL,
	human_read BOOLEAN NOT NULL,
	attempts INTEGER NOT NULL,
	next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
	request_id VARCHAR(200),
	last_error TEXT,
	summary TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (message_id, version, owner_id),
	FOREIGN KEY(message_id) REFERENCES mc_messages (id)
);

CREATE INDEX mc_delivery_due ON mc_deliveries (status, next_attempt_at);

CREATE TABLE mc_responses (
	id VARCHAR(32) NOT NULL,
	message_id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(100) NOT NULL,
	response VARCHAR(30) NOT NULL,
	note TEXT,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (message_id, owner_id),
	FOREIGN KEY(message_id) REFERENCES mc_messages (id)
);
