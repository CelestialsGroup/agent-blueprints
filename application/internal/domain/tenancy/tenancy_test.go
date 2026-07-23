package tenancy

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestTenantIDValidation(t *testing.T) {
	t.Parallel()

	if err := (TenantID("tenant-a")).Validate(); err != nil {
		t.Fatalf("valid tenant ID: %v", err)
	}
	if err := (TenantID("")).Validate(); !errors.Is(err, ErrMissingTenantContext) {
		t.Fatalf("empty tenant ID = %v, want ErrMissingTenantContext", err)
	}
	if err := (TenantID(strings.Repeat("x", 201))).Validate(); !errors.Is(err, ErrInvalidTenantID) {
		t.Fatalf("long tenant ID = %v, want ErrInvalidTenantID", err)
	}
	if err := (TenantID(strings.Repeat("租", 200))).Validate(); err != nil {
		t.Fatalf("200-character UTF-8 tenant ID: %v", err)
	}
}

func TestOwnershipValuesRequireCreationTime(t *testing.T) {
	t.Parallel()

	tenant := Tenant{ID: "tenant-a", DisplayName: "Tenant A"}
	if err := tenant.Validate(); !errors.Is(err, ErrInvalidCreatedAt) {
		t.Fatalf("tenant without created_at = %v, want ErrInvalidCreatedAt", err)
	}
	application := ClientApplication{
		TenantID: "tenant-a", ID: "client-a", DisplayName: "Client A",
	}
	if err := application.Validate(); !errors.Is(err, ErrInvalidCreatedAt) {
		t.Fatalf("client application without created_at = %v, want ErrInvalidCreatedAt", err)
	}
	tenant.CreatedAt = time.Date(2026, time.July, 23, 0, 0, 0, 0, time.UTC)
	application.CreatedAt = tenant.CreatedAt
	if err := tenant.Validate(); err != nil {
		t.Fatalf("tenant with created_at: %v", err)
	}
	if err := application.Validate(); err != nil {
		t.Fatalf("client application with created_at: %v", err)
	}
}
