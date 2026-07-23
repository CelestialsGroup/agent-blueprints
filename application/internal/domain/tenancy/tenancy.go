package tenancy

import (
	"errors"
	"fmt"
	"time"
	"unicode/utf8"
)

const maxIdentifierLength = 200

var (
	ErrMissingTenantContext = errors.New("tenant context is required")
	ErrInvalidTenantID      = errors.New("tenant ID is invalid")
	ErrInvalidClientAppID   = errors.New("client application ID is invalid")
	ErrInvalidDisplayName   = errors.New("display name is invalid")
	ErrInvalidCreatedAt     = errors.New("created_at is invalid")
)

type TenantID string

func (id TenantID) Validate() error {
	if id == "" {
		return ErrMissingTenantContext
	}
	if !utf8.ValidString(string(id)) || utf8.RuneCountInString(string(id)) > maxIdentifierLength {
		return fmt.Errorf("%w: length exceeds %d characters", ErrInvalidTenantID, maxIdentifierLength)
	}
	return nil
}

type ClientApplicationID string

func (id ClientApplicationID) Validate() error {
	if id == "" || !utf8.ValidString(string(id)) || utf8.RuneCountInString(string(id)) > maxIdentifierLength {
		return ErrInvalidClientAppID
	}
	return nil
}

type Tenant struct {
	ID          TenantID
	DisplayName string
	CreatedAt   time.Time
}

func (tenant Tenant) Validate() error {
	if err := tenant.ID.Validate(); err != nil {
		return err
	}
	if err := validateDisplayName(tenant.DisplayName); err != nil {
		return err
	}
	return validateCreatedAt(tenant.CreatedAt)
}

type ClientApplication struct {
	TenantID    TenantID
	ID          ClientApplicationID
	DisplayName string
	CreatedAt   time.Time
}

func (application ClientApplication) Validate() error {
	if err := application.TenantID.Validate(); err != nil {
		return err
	}
	if err := application.ID.Validate(); err != nil {
		return err
	}
	if err := validateDisplayName(application.DisplayName); err != nil {
		return err
	}
	return validateCreatedAt(application.CreatedAt)
}

func validateDisplayName(name string) error {
	if name == "" || !utf8.ValidString(name) || utf8.RuneCountInString(name) > maxIdentifierLength {
		return ErrInvalidDisplayName
	}
	return nil
}

func validateCreatedAt(createdAt time.Time) error {
	if createdAt.IsZero() {
		return ErrInvalidCreatedAt
	}
	return nil
}
