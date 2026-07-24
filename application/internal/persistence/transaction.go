package persistence

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
	"github.com/shell-echo/agent/internal/messaging"
)

var (
	ErrNestedTransaction            = errors.New("nested tenant transactions are not supported")
	ErrRepositoryOutsideTransaction = errors.New("tenant repository is outside its transaction")
)

type transactionContextKey struct{}

type transactionScope struct {
	tenantID tenancy.TenantID
	active   atomic.Bool
}

type TenantRepository interface {
	RegisterClientApplication(
		ctx context.Context,
		tenant tenancy.Tenant,
		application tenancy.ClientApplication,
	) (tenancy.ClientApplication, error)
	FindClientApplication(
		ctx context.Context,
		clientApplicationID tenancy.ClientApplicationID,
	) (tenancy.ClientApplication, error)
	EnqueueOutboxMessage(
		ctx context.Context,
		message messaging.OutboundMessage,
	) (messaging.EnqueueOutcome, error)
}

type TenantOperation func(context.Context, TenantRepository) error

type TransactionRunner struct {
	pool *pgxpool.Pool
}

func NewTransactionRunner(pool *pgxpool.Pool) (*TransactionRunner, error) {
	if pool == nil {
		return nil, errors.New("PostgreSQL pool is required")
	}
	return &TransactionRunner{pool: pool}, nil
}

func (runner *TransactionRunner) Run(
	ctx context.Context,
	tenantID tenancy.TenantID,
	operation TenantOperation,
) error {
	if operation == nil {
		return errors.New("tenant operation is required")
	}
	return runner.run(ctx, tenantID, func(ctx context.Context, repository *tenantRepository) error {
		return operation(ctx, repository)
	})
}

func (runner *TransactionRunner) run(
	ctx context.Context,
	tenantID tenancy.TenantID,
	operation func(context.Context, *tenantRepository) error,
) error {
	if ctx.Value(transactionContextKey{}) != nil {
		return ErrNestedTransaction
	}
	if err := tenantID.Validate(); err != nil {
		return err
	}

	tx, err := runner.pool.BeginTx(ctx, pgx.TxOptions{
		IsoLevel:   pgx.ReadCommitted,
		AccessMode: pgx.ReadWrite,
	})
	if err != nil {
		return fmt.Errorf("begin tenant transaction: %w", err)
	}

	committed := false
	defer func() {
		if !committed {
			rollbackCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = tx.Rollback(rollbackCtx)
		}
	}()

	if _, err := tx.Exec(
		ctx,
		"SELECT set_config('agent.tenant_id', $1, true)",
		string(tenantID),
	); err != nil {
		return fmt.Errorf("set transaction tenant context: %w", err)
	}

	scope := &transactionScope{tenantID: tenantID}
	scope.active.Store(true)
	defer scope.active.Store(false)
	tenantCtx := context.WithValue(ctx, transactionContextKey{}, scope)
	repository := &tenantRepository{
		tenantID: tenantID,
		queries:  agentdb.New(tx),
		scope:    scope,
	}
	if err := operation(tenantCtx, repository); err != nil {
		return err
	}
	scope.active.Store(false)
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit tenant transaction: %w", err)
	}
	committed = true
	return nil
}
