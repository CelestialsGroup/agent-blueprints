package messaging

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

type OutboxStore interface {
	Claim(context.Context, tenancy.TenantID, ClaimRequest) ([]ClaimedMessage, error)
	Renew(context.Context, tenancy.TenantID, LeaseReference, time.Duration) error
	Acknowledge(context.Context, tenancy.TenantID, LeaseReference) error
	Fail(context.Context, tenancy.TenantID, LeaseReference, Failure) error
}

type Transport interface {
	Send(context.Context, ClaimedMessage) error
}

type FailureClassifier func(error) (kind FailureKind, terminal bool)

type DispatcherConfig struct {
	WorkerID      string
	BatchSize     int32
	LeaseDuration time.Duration
	SendTimeout   time.Duration
	RetryDelay    time.Duration
	Classify      FailureClassifier
}

type DispatchReport struct {
	Claimed        int
	Succeeded      int
	RetryScheduled int
	TerminalFailed int
}

type Dispatcher struct {
	store     OutboxStore
	transport Transport
	config    DispatcherConfig
}

func NewDispatcher(store OutboxStore, transport Transport, config DispatcherConfig) (*Dispatcher, error) {
	if store == nil {
		return nil, errors.New("outbox store is required")
	}
	if transport == nil {
		return nil, errors.New("outbox transport is required")
	}
	if config.Classify == nil {
		return nil, errors.New("dispatcher failure classifier is required")
	}
	if config.SendTimeout <= 0 || config.SendTimeout >= config.LeaseDuration {
		return nil, errors.New("dispatcher send timeout must be positive and shorter than the lease")
	}
	if err := (ClaimRequest{
		WorkerID:      config.WorkerID,
		BatchSize:     config.BatchSize,
		LeaseDuration: config.LeaseDuration,
	}).Validate(); err != nil {
		return nil, err
	}
	if err := (Failure{Kind: "dispatcher_retry", RetryDelay: config.RetryDelay}).Validate(); err != nil {
		return nil, err
	}
	return &Dispatcher{store: store, transport: transport, config: config}, nil
}

func (dispatcher *Dispatcher) DispatchBatch(
	ctx context.Context,
	tenantID tenancy.TenantID,
) (DispatchReport, error) {
	if err := tenantID.Validate(); err != nil {
		return DispatchReport{}, err
	}
	messages, err := dispatcher.store.Claim(ctx, tenantID, ClaimRequest{
		WorkerID:      dispatcher.config.WorkerID,
		BatchSize:     dispatcher.config.BatchSize,
		LeaseDuration: dispatcher.config.LeaseDuration,
	})
	if err != nil {
		return DispatchReport{}, fmt.Errorf("claim outbox batch: %w", err)
	}

	report := DispatchReport{Claimed: len(messages)}
	if len(messages) > int(dispatcher.config.BatchSize) {
		return report, fmt.Errorf("%w: Store returned %d messages for a batch of %d", ErrInvalidDispatchBatch, len(messages), dispatcher.config.BatchSize)
	}
	messageIDs := make(map[string]struct{}, len(messages))
	for _, message := range messages {
		if err := message.Validate(tenantID, dispatcher.config.WorkerID); err != nil {
			return report, fmt.Errorf("validate claimed outbox message: %w", err)
		}
		if _, exists := messageIDs[message.MessageID]; exists {
			return report, fmt.Errorf("%w: Store returned duplicate message identity", ErrInvalidDispatchBatch)
		}
		messageIDs[message.MessageID] = struct{}{}
	}
	for _, message := range messages {
		lease := message.LeaseReference()
		attemptCtx, cancelAttempt := context.WithTimeout(ctx, dispatcher.config.SendTimeout)
		if err := dispatcher.store.Renew(
			attemptCtx,
			tenantID,
			lease,
			dispatcher.config.LeaseDuration,
		); err != nil {
			cancelAttempt()
			return report, fmt.Errorf("renew outbox message %q before send: %w", message.MessageID, err)
		}
		if err := attemptCtx.Err(); err != nil {
			cancelAttempt()
			return report, fmt.Errorf("renew outbox message %q left no transport budget: %w", message.MessageID, err)
		}

		deliveryErr := dispatcher.transport.Send(attemptCtx, message)
		cancelAttempt()
		if deliveryErr == nil {
			if err := dispatcher.store.Acknowledge(
				ctx,
				tenantID,
				lease,
			); err != nil {
				return report, fmt.Errorf("acknowledge outbox message %q: %w", message.MessageID, err)
			}
			report.Succeeded++
			continue
		}

		kind, terminal := dispatcher.config.Classify(deliveryErr)
		failure := Failure{Kind: kind, Terminal: terminal}
		if !terminal {
			failure.RetryDelay = dispatcher.config.RetryDelay
		}
		if err := failure.Validate(); err != nil {
			return report, fmt.Errorf("classify outbox failure for %q: %w", message.MessageID, err)
		}
		if err := dispatcher.store.Fail(
			ctx,
			tenantID,
			lease,
			failure,
		); err != nil {
			return report, fmt.Errorf("record outbox failure for %q: %w", message.MessageID, err)
		}
		if terminal {
			report.TerminalFailed++
		} else {
			report.RetryScheduled++
		}
	}
	return report, nil
}
