package persistence

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
	"github.com/shell-echo/agent/internal/messaging"
)

type OutboxRepository struct {
	runner *TransactionRunner
}

func NewOutboxRepository(runner *TransactionRunner) (*OutboxRepository, error) {
	if runner == nil {
		return nil, errors.New("transaction runner is required")
	}
	return &OutboxRepository{runner: runner}, nil
}

func (repository *OutboxRepository) Claim(
	ctx context.Context,
	tenantID tenancy.TenantID,
	request messaging.ClaimRequest,
) ([]messaging.ClaimedMessage, error) {
	if err := request.Validate(); err != nil {
		return nil, err
	}
	var claimed []messaging.ClaimedMessage
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := request.WorkerID
		rows, err := txRepository.queries.ClaimOutboxMessages(ctx, agentdb.ClaimOutboxMessagesParams{
			WorkerID:      &workerID,
			LeaseDuration: databaseInterval(request.LeaseDuration),
			TenantID:      string(tenantID),
			BatchSize:     request.BatchSize,
		})
		if err != nil {
			return fmt.Errorf("claim outbox messages: %w", err)
		}
		claimed = make([]messaging.ClaimedMessage, 0, len(rows))
		for _, row := range rows {
			message, err := mapClaimedMessage(row, tenantID, request.WorkerID)
			if err != nil {
				return err
			}
			claimed = append(claimed, message)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(claimed, func(left, right int) bool {
		return claimed[left].MessageID < claimed[right].MessageID
	})
	return claimed, nil
}

func (repository *OutboxRepository) Renew(
	ctx context.Context,
	tenantID tenancy.TenantID,
	lease messaging.LeaseReference,
	leaseDuration time.Duration,
) error {
	if err := lease.Validate(); err != nil {
		return err
	}
	if err := (messaging.ClaimRequest{
		WorkerID:      lease.WorkerID,
		BatchSize:     1,
		LeaseDuration: leaseDuration,
	}).Validate(); err != nil {
		return errors.Join(messaging.ErrInvalidLease, err)
	}
	return repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := lease.WorkerID
		_, err := txRepository.queries.RenewOutboxLease(ctx, agentdb.RenewOutboxLeaseParams{
			LeaseDuration: databaseInterval(leaseDuration),
			TenantID:      string(tenantID),
			MessageID:     lease.MessageID,
			WorkerID:      &workerID,
			FencingToken:  lease.FencingToken,
		})
		return classifyLeaseMutation("renew outbox lease", err)
	})
}

func (repository *OutboxRepository) Acknowledge(
	ctx context.Context,
	tenantID tenancy.TenantID,
	lease messaging.LeaseReference,
) error {
	if err := lease.Validate(); err != nil {
		return err
	}
	return repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := lease.WorkerID
		_, err := txRepository.queries.AcknowledgeOutboxMessage(ctx, agentdb.AcknowledgeOutboxMessageParams{
			TenantID:     string(tenantID),
			MessageID:    lease.MessageID,
			WorkerID:     &workerID,
			FencingToken: lease.FencingToken,
		})
		return classifyLeaseMutation("acknowledge outbox message", err)
	})
}

func (repository *OutboxRepository) Fail(
	ctx context.Context,
	tenantID tenancy.TenantID,
	lease messaging.LeaseReference,
	failure messaging.Failure,
) error {
	if err := lease.Validate(); err != nil {
		return err
	}
	if err := failure.Validate(); err != nil {
		return err
	}
	return repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := lease.WorkerID
		errorKind := string(failure.Kind)
		if failure.Terminal {
			_, err := txRepository.queries.FailOutboxMessageTerminal(ctx, agentdb.FailOutboxMessageTerminalParams{
				TenantID:     string(tenantID),
				MessageID:    lease.MessageID,
				ErrorKind:    &errorKind,
				WorkerID:     &workerID,
				FencingToken: lease.FencingToken,
			})
			return classifyLeaseMutation("terminally fail outbox message", err)
		}
		_, err := txRepository.queries.FailOutboxMessageRetryable(ctx, agentdb.FailOutboxMessageRetryableParams{
			RetryDelay:   databaseInterval(failure.RetryDelay),
			ErrorKind:    &errorKind,
			TenantID:     string(tenantID),
			MessageID:    lease.MessageID,
			WorkerID:     &workerID,
			FencingToken: lease.FencingToken,
		})
		return classifyLeaseMutation("retryably fail outbox message", err)
	})
}

func (repository *OutboxRepository) Status(
	ctx context.Context,
	tenantID tenancy.TenantID,
	messageID string,
) (messaging.OutboxStatus, error) {
	if err := tenantID.Validate(); err != nil {
		return messaging.OutboxStatus{}, err
	}
	if err := messaging.ValidateMessageID(messageID); err != nil {
		return messaging.OutboxStatus{}, err
	}
	var status messaging.OutboxStatus
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		row, err := txRepository.queries.GetOutboxMessage(ctx, agentdb.GetOutboxMessageParams{
			TenantID:  string(tenantID),
			MessageID: messageID,
		})
		if errors.Is(err, pgx.ErrNoRows) {
			return messaging.ErrMessagingNotFound
		}
		if err != nil {
			return fmt.Errorf("read outbox status: %w", err)
		}
		status = mapOutboxStatus(row)
		return nil
	})
	return status, err
}

type InboxEffect func(context.Context, TenantRepository) error

type InboxConsumer struct {
	runner *TransactionRunner
}

func NewInboxConsumer(runner *TransactionRunner) (*InboxConsumer, error) {
	if runner == nil {
		return nil, errors.New("transaction runner is required")
	}
	return &InboxConsumer{runner: runner}, nil
}

func (consumer *InboxConsumer) Consume(
	ctx context.Context,
	tenantID tenancy.TenantID,
	message messaging.InboundMessage,
	completedAt time.Time,
	effect InboxEffect,
) (messaging.ConsumeOutcome, error) {
	if err := message.Validate(tenantID); err != nil {
		return "", err
	}
	if effect == nil {
		return "", errors.New("inbox effect is required")
	}
	completedAt = databaseTime(completedAt)
	if completedAt.Before(databaseTime(message.ReceivedAt)) {
		return "", fmt.Errorf("%w: completed_at precedes received_at", messaging.ErrInvalidMessage)
	}

	var outcome messaging.ConsumeOutcome
	err := consumer.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		row, inserted, err := insertOrFindInboxMessage(ctx, txRepository, tenantID, message)
		if err != nil {
			return err
		}
		if !inserted {
			if err := verifyInboxReplay(row, message); err != nil {
				return err
			}
			if row.State != "completed" || !row.CompletedAt.Valid {
				return fmt.Errorf("%w: existing inbox message is not completed", messaging.ErrInboxConflict)
			}
			outcome = messaging.ConsumeReplay
			return nil
		}

		if err := effect(ctx, txRepository); err != nil {
			return err
		}
		if _, err := txRepository.queries.CompleteInboxMessage(ctx, agentdb.CompleteInboxMessageParams{
			CompletedAt: timestamp(completedAt),
			TenantID:    string(tenantID),
			Consumer:    message.Consumer,
			MessageID:   message.MessageID,
		}); err != nil {
			return fmt.Errorf("complete inbox message: %w", err)
		}
		outcome = messaging.ConsumeApplied
		return nil
	})
	return outcome, err
}

func (repository *tenantRepository) EnqueueOutboxMessage(
	ctx context.Context,
	message messaging.OutboundMessage,
) (messaging.EnqueueOutcome, error) {
	if err := repository.requireTransaction(ctx); err != nil {
		return "", err
	}
	if err := message.Validate(); err != nil {
		return "", err
	}
	row, err := repository.queries.EnqueueOutboxMessage(ctx, agentdb.EnqueueOutboxMessageParams{
		TenantID:      string(repository.tenantID),
		MessageID:     message.MessageID,
		Destination:   message.Destination,
		Payload:       message.Payload,
		PayloadDigest: message.PayloadDigest,
		NextAttemptAt: timestamp(databaseTime(message.AvailableAt)),
		CreatedAt:     timestamp(databaseTime(message.CreatedAt)),
	})
	if err == nil {
		return messaging.EnqueueInserted, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return "", fmt.Errorf("enqueue outbox message: %w", err)
	}
	row, err = repository.queries.GetOutboxMessage(ctx, agentdb.GetOutboxMessageParams{
		TenantID:  string(repository.tenantID),
		MessageID: message.MessageID,
	})
	if errors.Is(err, pgx.ErrNoRows) {
		return "", messaging.ErrOutboxConflict
	}
	if err != nil {
		return "", fmt.Errorf("read conflicting outbox message: %w", err)
	}
	if row.Destination != message.Destination ||
		row.PayloadDigest != message.PayloadDigest ||
		!bytes.Equal(row.Payload, message.Payload) ||
		!row.NextAttemptAt.Time.Equal(databaseTime(message.AvailableAt)) ||
		!row.CreatedAt.Time.Equal(databaseTime(message.CreatedAt)) {
		return "", fmt.Errorf("%w: %q", messaging.ErrOutboxConflict, message.MessageID)
	}
	return messaging.EnqueueReplay, nil
}

func insertOrFindInboxMessage(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	message messaging.InboundMessage,
) (agentdb.AgentTransportInboxMessage, bool, error) {
	parameters := agentdb.InsertInboxMessageParams{
		TenantID:      string(tenantID),
		Consumer:      message.Consumer,
		MessageID:     message.MessageID,
		PayloadDigest: message.PayloadDigest,
		ReceivedAt:    timestamp(databaseTime(message.ReceivedAt)),
	}
	row, err := repository.queries.InsertInboxMessage(ctx, parameters)
	if err == nil {
		return row, true, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return agentdb.AgentTransportInboxMessage{}, false, fmt.Errorf("insert inbox message: %w", err)
	}

	row, err = repository.queries.GetInboxMessageByTransportIdentity(
		ctx,
		agentdb.GetInboxMessageByTransportIdentityParams{
			TenantID:  string(tenantID),
			Consumer:  message.Consumer,
			MessageID: message.MessageID,
		},
	)
	if err == nil {
		return row, false, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return agentdb.AgentTransportInboxMessage{}, false, fmt.Errorf("read transport inbox conflict: %w", err)
	}
	return agentdb.AgentTransportInboxMessage{}, false, messaging.ErrInboxConflict
}

func verifyInboxReplay(row agentdb.AgentTransportInboxMessage, message messaging.InboundMessage) error {
	if row.PayloadDigest != message.PayloadDigest {
		return fmt.Errorf("%w: %q", messaging.ErrInboxDigestConflict, message.MessageID)
	}
	if row.Consumer != message.Consumer {
		return messaging.ErrInboxConflict
	}
	return nil
}

func mapClaimedMessage(
	row agentdb.AgentOutboxMessage,
	tenantID tenancy.TenantID,
	workerID string,
) (messaging.ClaimedMessage, error) {
	if row.LeaseWorkerID == nil || !row.LeaseExpiresAt.Valid {
		return messaging.ClaimedMessage{}, errors.New("claimed outbox row lacks lease ownership")
	}
	message := messaging.ClaimedMessage{
		TenantID:       tenancy.TenantID(row.TenantID),
		MessageID:      row.MessageID,
		Destination:    row.Destination,
		Payload:        append([]byte(nil), row.Payload...),
		PayloadDigest:  row.PayloadDigest,
		AttemptCount:   row.AttemptCount,
		LeaseWorkerID:  *row.LeaseWorkerID,
		FencingToken:   row.LeaseFencingToken,
		LeaseExpiresAt: row.LeaseExpiresAt.Time,
	}
	if err := message.Validate(tenantID, workerID); err != nil {
		return messaging.ClaimedMessage{}, fmt.Errorf("map claimed outbox message: %w", err)
	}
	return message, nil
}

func mapOutboxStatus(row agentdb.AgentOutboxMessage) messaging.OutboxStatus {
	status := messaging.OutboxStatus{
		TenantID:      tenancy.TenantID(row.TenantID),
		MessageID:     row.MessageID,
		State:         messaging.OutboxState(row.State),
		AttemptCount:  row.AttemptCount,
		FencingToken:  row.LeaseFencingToken,
		NextAttemptAt: row.NextAttemptAt.Time,
	}
	if row.LeaseWorkerID != nil {
		status.LeaseWorkerID = *row.LeaseWorkerID
	}
	if row.LeaseExpiresAt.Valid {
		status.LeaseExpiresAt = row.LeaseExpiresAt.Time
	}
	if row.LastErrorKind != nil {
		status.LastErrorKind = messaging.FailureKind(*row.LastErrorKind)
	}
	if row.SucceededAt.Valid {
		status.SucceededAt = row.SucceededAt.Time
	}
	if row.TerminalFailedAt.Valid {
		status.TerminalFailedAt = row.TerminalFailedAt.Time
	}
	return status
}

func classifyLeaseMutation(operation string, err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return messaging.ErrLeaseLost
	}
	if err != nil {
		return fmt.Errorf("%s: %w", operation, err)
	}
	return nil
}

func databaseTime(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC().Truncate(time.Microsecond)
}

func databaseInterval(value time.Duration) pgtype.Interval {
	return pgtype.Interval{Microseconds: value.Microseconds(), Valid: true}
}
