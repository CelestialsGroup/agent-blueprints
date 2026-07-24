-- +goose Up
SET ROLE agent_migrator;

CREATE TABLE agent.outbox_messages (
    tenant_id varchar(200) NOT NULL,
    message_id varchar(200) NOT NULL,
    destination varchar(200) NOT NULL,
    payload bytea NOT NULL,
    payload_digest varchar(71) NOT NULL,
    state varchar(32) NOT NULL DEFAULT 'pending',
    attempt_count bigint NOT NULL DEFAULT 0,
    lease_fencing_token bigint NOT NULL DEFAULT 0,
    lease_worker_id varchar(200),
    lease_expires_at timestamptz,
    next_attempt_at timestamptz NOT NULL,
    last_error_kind varchar(200),
    last_error_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    succeeded_at timestamptz,
    terminal_failed_at timestamptz,
    CONSTRAINT outbox_messages_pk PRIMARY KEY (tenant_id, message_id),
    CONSTRAINT outbox_messages_transport_identity_uk UNIQUE (message_id),
    CONSTRAINT outbox_messages_tenant_fk
        FOREIGN KEY (tenant_id)
        REFERENCES agent.tenants (tenant_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT outbox_messages_tenant_id_not_blank CHECK (tenant_id <> ''),
    CONSTRAINT outbox_messages_message_id_not_blank CHECK (message_id <> ''),
    CONSTRAINT outbox_messages_destination_not_blank CHECK (destination <> ''),
    CONSTRAINT outbox_messages_payload_size CHECK (octet_length(payload) BETWEEN 1 AND 1048576),
    CONSTRAINT outbox_messages_payload_digest CHECK (
        payload_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT outbox_messages_state CHECK (
        state IN ('pending', 'leased', 'succeeded', 'terminal_failed')
    ),
    CONSTRAINT outbox_messages_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT outbox_messages_fencing_token CHECK (
        lease_fencing_token >= 0 AND lease_fencing_token = attempt_count
    ),
    CONSTRAINT outbox_messages_error_pair CHECK (
        (last_error_kind IS NULL) = (last_error_at IS NULL)
    ),
    CONSTRAINT outbox_messages_error_kind CHECK (
        last_error_kind IS NULL OR (
            octet_length(last_error_kind) BETWEEN 1 AND 200
            AND left(last_error_kind, 1) COLLATE "C" ~ '[a-z]'
            AND last_error_kind COLLATE "C" !~ '[^a-z0-9_]'
        )
    ),
    CONSTRAINT outbox_messages_state_fields CHECK (
        (
            state = 'pending'
            AND lease_worker_id IS NULL
            AND lease_expires_at IS NULL
            AND succeeded_at IS NULL
            AND terminal_failed_at IS NULL
        ) OR (
            state = 'leased'
            AND attempt_count > 0
            AND lease_worker_id IS NOT NULL
            AND lease_worker_id <> ''
            AND lease_expires_at IS NOT NULL
            AND lease_expires_at > updated_at
            AND succeeded_at IS NULL
            AND terminal_failed_at IS NULL
        ) OR (
            state = 'succeeded'
            AND lease_worker_id IS NULL
            AND lease_expires_at IS NULL
            AND succeeded_at IS NOT NULL
            AND terminal_failed_at IS NULL
        ) OR (
            state = 'terminal_failed'
            AND lease_worker_id IS NULL
            AND lease_expires_at IS NULL
            AND succeeded_at IS NULL
            AND terminal_failed_at IS NOT NULL
            AND last_error_kind IS NOT NULL
        )
    ),
    CONSTRAINT outbox_messages_timestamps CHECK (
        next_attempt_at >= created_at
        AND updated_at >= created_at
        AND (succeeded_at IS NULL OR succeeded_at >= created_at)
        AND (terminal_failed_at IS NULL OR terminal_failed_at >= created_at)
    )
);

CREATE INDEX outbox_messages_pending_claim_idx
    ON agent.outbox_messages (tenant_id, next_attempt_at, created_at, message_id)
    WHERE state = 'pending';

CREATE INDEX outbox_messages_expired_lease_idx
    ON agent.outbox_messages (tenant_id, lease_expires_at, created_at, message_id)
    WHERE state = 'leased';

CREATE INDEX outbox_messages_reconciliation_idx
    ON agent.outbox_messages (tenant_id, state, updated_at, message_id)
    WHERE state IN ('leased', 'terminal_failed');

CREATE TABLE agent.transport_inbox_messages (
    tenant_id varchar(200) NOT NULL,
    consumer varchar(200) NOT NULL,
    message_id varchar(200) NOT NULL,
    payload_digest varchar(71) NOT NULL,
    state varchar(32) NOT NULL,
    received_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT transport_inbox_messages_pk PRIMARY KEY (tenant_id, consumer, message_id),
    CONSTRAINT transport_inbox_messages_transport_identity_uk UNIQUE (consumer, message_id),
    CONSTRAINT transport_inbox_messages_tenant_fk
        FOREIGN KEY (tenant_id)
        REFERENCES agent.tenants (tenant_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT transport_inbox_messages_tenant_id_not_blank CHECK (tenant_id <> ''),
    CONSTRAINT transport_inbox_messages_consumer_not_blank CHECK (consumer <> ''),
    CONSTRAINT transport_inbox_messages_message_id_not_blank CHECK (message_id <> ''),
    CONSTRAINT transport_inbox_messages_payload_digest CHECK (
        payload_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT transport_inbox_messages_state CHECK (state IN ('processing', 'completed')),
    CONSTRAINT transport_inbox_messages_state_fields CHECK (
        (state = 'processing' AND completed_at IS NULL)
        OR (state = 'completed' AND completed_at IS NOT NULL)
    ),
    CONSTRAINT transport_inbox_messages_timestamps CHECK (
        completed_at IS NULL OR completed_at >= received_at
    )
);

CREATE INDEX transport_inbox_messages_reconciliation_idx
    ON agent.transport_inbox_messages (tenant_id, state, received_at, consumer, message_id);

ALTER TABLE agent.outbox_messages OWNER TO agent_migrator;
ALTER TABLE agent.transport_inbox_messages OWNER TO agent_migrator;

ALTER TABLE agent.outbox_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.outbox_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY outbox_messages_tenant_isolation ON agent.outbox_messages
    FOR ALL
    TO agent_app
    USING (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    )
    WITH CHECK (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    );

ALTER TABLE agent.transport_inbox_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.transport_inbox_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY transport_inbox_messages_tenant_isolation ON agent.transport_inbox_messages
    FOR ALL
    TO agent_app
    USING (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    )
    WITH CHECK (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    );

GRANT SELECT ON TABLE
    agent.outbox_messages,
    agent.transport_inbox_messages
TO agent_app;

GRANT INSERT (
    tenant_id,
    message_id,
    destination,
    payload,
    payload_digest,
    next_attempt_at,
    created_at,
    updated_at
) ON agent.outbox_messages TO agent_app;

GRANT UPDATE (
    state,
    attempt_count,
    lease_fencing_token,
    lease_worker_id,
    lease_expires_at,
    next_attempt_at,
    last_error_kind,
    last_error_at,
    updated_at,
    succeeded_at,
    terminal_failed_at
) ON agent.outbox_messages TO agent_app;

GRANT INSERT (
    tenant_id,
    consumer,
    message_id,
    payload_digest,
    state,
    received_at
) ON agent.transport_inbox_messages TO agent_app;

GRANT UPDATE (
    state,
    completed_at
) ON agent.transport_inbox_messages TO agent_app;

RESET ROLE;

-- +goose Down
SET ROLE agent_migrator;

-- Data-bearing durable messaging tables are authoritative ledgers. Only an empty
-- expansion can be removed safely; otherwise recovery requires a forward migration.
-- The NOLOGIN owner has no BYPASSRLS. Temporarily removing FORCE is transaction-local
-- when the guard raises, and lets the owner inspect all rows without a wildcard Tenant.
ALTER TABLE agent.outbox_messages NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.transport_inbox_messages NO FORCE ROW LEVEL SECURITY;

-- +goose StatementBegin
DO $safe_empty_down$
BEGIN
    IF EXISTS (SELECT 1 FROM agent.outbox_messages)
       OR EXISTS (SELECT 1 FROM agent.transport_inbox_messages) THEN
        RAISE EXCEPTION USING
            ERRCODE = '0A000',
            MESSAGE = '00002_postgresql_durable_messaging contains durable data and is forward-only';
    END IF;
END
$safe_empty_down$;
-- +goose StatementEnd

DROP TABLE agent.transport_inbox_messages;
DROP TABLE agent.outbox_messages;

RESET ROLE;
