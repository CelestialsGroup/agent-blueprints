-- name: EnqueueOutboxMessage :one
INSERT INTO agent.outbox_messages (
    tenant_id,
    message_id,
    destination,
    payload,
    payload_digest,
    next_attempt_at,
    created_at,
    updated_at
) VALUES (
    sqlc.arg(tenant_id),
    sqlc.arg(message_id),
    sqlc.arg(destination),
    sqlc.arg(payload),
    sqlc.arg(payload_digest),
    sqlc.arg(next_attempt_at),
    sqlc.arg(created_at),
    sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetOutboxMessage :one
SELECT *
FROM agent.outbox_messages
WHERE tenant_id = sqlc.arg(tenant_id)
  AND message_id = sqlc.arg(message_id);

-- name: ClaimOutboxMessages :many
WITH eligibility_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
),
candidates AS MATERIALIZED (
    SELECT candidate_messages.tenant_id, candidate_messages.message_id
    FROM agent.outbox_messages AS candidate_messages
    CROSS JOIN eligibility_time
    WHERE candidate_messages.tenant_id = sqlc.arg(tenant_id)
      AND (
          (candidate_messages.state = 'pending' AND candidate_messages.next_attempt_at <= eligibility_time.occurred_at)
          OR (candidate_messages.state = 'leased' AND candidate_messages.lease_expires_at <= eligibility_time.occurred_at)
      )
    ORDER BY
        CASE
            WHEN candidate_messages.state = 'pending' THEN candidate_messages.next_attempt_at
            ELSE candidate_messages.lease_expires_at
        END,
        candidate_messages.created_at,
        candidate_messages.message_id
    FOR UPDATE OF candidate_messages SKIP LOCKED
    LIMIT sqlc.arg(batch_size)
),
claim_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM (SELECT count(*) FROM candidates) AS locked_candidates
)
UPDATE agent.outbox_messages AS messages
SET state = 'leased',
    attempt_count = messages.attempt_count + 1,
    lease_fencing_token = messages.lease_fencing_token + 1,
    lease_worker_id = sqlc.arg(worker_id),
    lease_expires_at = claim_time.occurred_at + sqlc.arg(lease_duration)::interval,
    updated_at = claim_time.occurred_at
FROM candidates
CROSS JOIN claim_time
WHERE messages.tenant_id = candidates.tenant_id
  AND messages.message_id = candidates.message_id
RETURNING messages.*;

-- name: RenewOutboxLease :one
WITH locked_lease AS MATERIALIZED (
    SELECT messages.tenant_id, messages.message_id, messages.lease_expires_at
    FROM agent.outbox_messages AS messages
    WHERE messages.tenant_id = sqlc.arg(tenant_id)
      AND messages.message_id = sqlc.arg(message_id)
      AND messages.state = 'leased'
      AND messages.lease_worker_id = sqlc.arg(worker_id)
      AND messages.lease_fencing_token = sqlc.arg(fencing_token)
    FOR UPDATE OF messages
),
operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM locked_lease
)
UPDATE agent.outbox_messages AS messages
SET lease_expires_at = GREATEST(
        locked_lease.lease_expires_at,
        operation_time.occurred_at + sqlc.arg(lease_duration)::interval
    ),
    updated_at = operation_time.occurred_at
FROM locked_lease
CROSS JOIN operation_time
WHERE messages.tenant_id = locked_lease.tenant_id
  AND messages.message_id = locked_lease.message_id
  AND locked_lease.lease_expires_at > operation_time.occurred_at
RETURNING messages.*;

-- name: AcknowledgeOutboxMessage :one
WITH locked_lease AS MATERIALIZED (
    SELECT messages.tenant_id, messages.message_id, messages.lease_expires_at
    FROM agent.outbox_messages AS messages
    WHERE messages.tenant_id = sqlc.arg(tenant_id)
      AND messages.message_id = sqlc.arg(message_id)
      AND messages.state = 'leased'
      AND messages.lease_worker_id = sqlc.arg(worker_id)
      AND messages.lease_fencing_token = sqlc.arg(fencing_token)
    FOR UPDATE OF messages
),
operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM locked_lease
)
UPDATE agent.outbox_messages AS messages
SET state = 'succeeded',
    lease_worker_id = NULL,
    lease_expires_at = NULL,
    updated_at = operation_time.occurred_at,
    succeeded_at = operation_time.occurred_at
FROM locked_lease
CROSS JOIN operation_time
WHERE messages.tenant_id = locked_lease.tenant_id
  AND messages.message_id = locked_lease.message_id
  AND locked_lease.lease_expires_at > operation_time.occurred_at
RETURNING messages.*;

-- name: FailOutboxMessageRetryable :one
WITH locked_lease AS MATERIALIZED (
    SELECT messages.tenant_id, messages.message_id, messages.lease_expires_at
    FROM agent.outbox_messages AS messages
    WHERE messages.tenant_id = sqlc.arg(tenant_id)
      AND messages.message_id = sqlc.arg(message_id)
      AND messages.state = 'leased'
      AND messages.lease_worker_id = sqlc.arg(worker_id)
      AND messages.lease_fencing_token = sqlc.arg(fencing_token)
    FOR UPDATE OF messages
),
operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM locked_lease
)
UPDATE agent.outbox_messages AS messages
SET state = 'pending',
    lease_worker_id = NULL,
    lease_expires_at = NULL,
    next_attempt_at = operation_time.occurred_at + sqlc.arg(retry_delay)::interval,
    last_error_kind = sqlc.arg(error_kind),
    last_error_at = operation_time.occurred_at,
    updated_at = operation_time.occurred_at
FROM locked_lease
CROSS JOIN operation_time
WHERE messages.tenant_id = locked_lease.tenant_id
  AND messages.message_id = locked_lease.message_id
  AND locked_lease.lease_expires_at > operation_time.occurred_at
RETURNING messages.*;

-- name: FailOutboxMessageTerminal :one
WITH locked_lease AS MATERIALIZED (
    SELECT messages.tenant_id, messages.message_id, messages.lease_expires_at
    FROM agent.outbox_messages AS messages
    WHERE messages.tenant_id = sqlc.arg(tenant_id)
      AND messages.message_id = sqlc.arg(message_id)
      AND messages.state = 'leased'
      AND messages.lease_worker_id = sqlc.arg(worker_id)
      AND messages.lease_fencing_token = sqlc.arg(fencing_token)
    FOR UPDATE OF messages
),
operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM locked_lease
)
UPDATE agent.outbox_messages AS messages
SET state = 'terminal_failed',
    lease_worker_id = NULL,
    lease_expires_at = NULL,
    last_error_kind = sqlc.arg(error_kind),
    last_error_at = operation_time.occurred_at,
    updated_at = operation_time.occurred_at,
    terminal_failed_at = operation_time.occurred_at
FROM locked_lease
CROSS JOIN operation_time
WHERE messages.tenant_id = locked_lease.tenant_id
  AND messages.message_id = locked_lease.message_id
  AND locked_lease.lease_expires_at > operation_time.occurred_at
RETURNING messages.*;

-- name: InsertInboxMessage :one
INSERT INTO agent.transport_inbox_messages (
    tenant_id,
    consumer,
    message_id,
    payload_digest,
    state,
    received_at
) VALUES (
    sqlc.arg(tenant_id),
    sqlc.arg(consumer),
    sqlc.arg(message_id),
    sqlc.arg(payload_digest),
    'processing',
    sqlc.arg(received_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetInboxMessageByTransportIdentity :one
SELECT *
FROM agent.transport_inbox_messages
WHERE tenant_id = sqlc.arg(tenant_id)
  AND consumer = sqlc.arg(consumer)
  AND message_id = sqlc.arg(message_id);

-- name: CompleteInboxMessage :one
UPDATE agent.transport_inbox_messages
SET state = 'completed',
    completed_at = sqlc.arg(completed_at)
WHERE tenant_id = sqlc.arg(tenant_id)
  AND consumer = sqlc.arg(consumer)
  AND message_id = sqlc.arg(message_id)
  AND state = 'processing'
RETURNING *;
