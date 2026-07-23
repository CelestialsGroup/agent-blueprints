package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
)

var (
	ErrNotFound       = errors.New("persistence object not found")
	ErrTenantConflict = errors.New("tenant metadata conflicts with the existing tenant")
)

type TenantConflictError struct {
	TenantID tenancy.TenantID
}

// Error reports the tenant whose immutable bootstrap metadata did not match.
func (err *TenantConflictError) Error() string {
	return fmt.Sprintf("%s: %s", ErrTenantConflict, err.TenantID)
}

// Unwrap exposes ErrTenantConflict for stable error-category checks.
func (err *TenantConflictError) Unwrap() error {
	return ErrTenantConflict
}

type ClientApplicationRepository struct {
	runner *TransactionRunner
}

func NewClientApplicationRepository(runner *TransactionRunner) (*ClientApplicationRepository, error) {
	if runner == nil {
		return nil, errors.New("transaction runner is required")
	}
	return &ClientApplicationRepository{runner: runner}, nil
}

func (repository *ClientApplicationRepository) Register(
	ctx context.Context,
	tenant tenancy.Tenant,
	application tenancy.ClientApplication,
) (tenancy.ClientApplication, error) {
	var registered tenancy.ClientApplication
	err := repository.runner.Run(ctx, tenant.ID, func(
		ctx context.Context,
		tenantRepository TenantRepository,
	) error {
		var err error
		registered, err = tenantRepository.RegisterClientApplication(ctx, tenant, application)
		return err
	})
	return registered, err
}

func (repository *ClientApplicationRepository) Find(
	ctx context.Context,
	tenantID tenancy.TenantID,
	clientApplicationID tenancy.ClientApplicationID,
) (tenancy.ClientApplication, error) {
	var application tenancy.ClientApplication
	err := repository.runner.Run(ctx, tenantID, func(
		ctx context.Context,
		tenantRepository TenantRepository,
	) error {
		var err error
		application, err = tenantRepository.FindClientApplication(ctx, clientApplicationID)
		return err
	})
	return application, err
}

type tenantRepository struct {
	tenantID tenancy.TenantID
	queries  *agentdb.Queries
	scope    *transactionScope
}

func (repository *tenantRepository) RegisterClientApplication(
	ctx context.Context,
	tenant tenancy.Tenant,
	application tenancy.ClientApplication,
) (tenancy.ClientApplication, error) {
	if err := repository.requireTransaction(ctx); err != nil {
		return tenancy.ClientApplication{}, err
	}
	if err := tenant.Validate(); err != nil {
		return tenancy.ClientApplication{}, err
	}
	if err := application.Validate(); err != nil {
		return tenancy.ClientApplication{}, err
	}
	if tenant.ID != repository.tenantID || application.TenantID != repository.tenantID {
		return tenancy.ClientApplication{}, tenancy.ErrInvalidTenantID
	}

	tenantRow, err := repository.queries.EnsureTenant(ctx, agentdb.EnsureTenantParams{
		TenantID:    string(repository.tenantID),
		DisplayName: tenant.DisplayName,
		CreatedAt:   timestamp(tenant.CreatedAt),
	})
	if errors.Is(err, pgx.ErrNoRows) {
		tenantRow, err = repository.queries.GetTenant(ctx, string(repository.tenantID))
	}
	if err != nil {
		return tenancy.ClientApplication{}, fmt.Errorf("ensure tenant: %w", err)
	}
	if tenantRow.DisplayName != tenant.DisplayName ||
		!tenantRow.CreatedAt.Time.Equal(tenant.CreatedAt.Truncate(time.Microsecond)) {
		return tenancy.ClientApplication{}, &TenantConflictError{TenantID: repository.tenantID}
	}

	row, err := repository.queries.CreateClientApplication(
		ctx,
		agentdb.CreateClientApplicationParams{
			TenantID:    string(repository.tenantID),
			ClientAppID: string(application.ID),
			DisplayName: application.DisplayName,
			CreatedAt:   timestamp(application.CreatedAt),
		},
	)
	if err != nil {
		return tenancy.ClientApplication{}, fmt.Errorf("create client application: %w", err)
	}
	return mapClientApplication(row), nil
}

func (repository *tenantRepository) FindClientApplication(
	ctx context.Context,
	clientApplicationID tenancy.ClientApplicationID,
) (tenancy.ClientApplication, error) {
	if err := repository.requireTransaction(ctx); err != nil {
		return tenancy.ClientApplication{}, err
	}
	if err := clientApplicationID.Validate(); err != nil {
		return tenancy.ClientApplication{}, err
	}
	row, err := repository.queries.GetClientApplication(
		ctx,
		agentdb.GetClientApplicationParams{
			TenantID:    string(repository.tenantID),
			ClientAppID: string(clientApplicationID),
		},
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return tenancy.ClientApplication{}, ErrNotFound
	}
	if err != nil {
		return tenancy.ClientApplication{}, fmt.Errorf("find client application: %w", err)
	}
	return mapClientApplication(row), nil
}

func (repository *tenantRepository) requireTransaction(ctx context.Context) error {
	scope, ok := ctx.Value(transactionContextKey{}).(*transactionScope)
	if !ok || scope != repository.scope || scope.tenantID != repository.tenantID || !scope.active.Load() {
		return ErrRepositoryOutsideTransaction
	}
	return nil
}

func mapClientApplication(row agentdb.AgentClientApplication) tenancy.ClientApplication {
	return tenancy.ClientApplication{
		TenantID:    tenancy.TenantID(row.TenantID),
		ID:          tenancy.ClientApplicationID(row.ClientAppID),
		DisplayName: row.DisplayName,
		CreatedAt:   row.CreatedAt.Time,
	}
}

func timestamp(value time.Time) pgtype.Timestamptz {
	return pgtype.Timestamptz{Time: value, Valid: true}
}
