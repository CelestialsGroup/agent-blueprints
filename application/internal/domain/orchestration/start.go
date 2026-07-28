package orchestration

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

var ErrInvalidStartRequest = errors.New("invalid orchestration start request")

const maxStartIdentifierBytes = 200

var startDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// StartRequest is the framework-neutral identity allocated before orchestration start.
// It carries no engine endpoint, namespace, or native execution identifier.
type StartRequest struct {
	TenantID            tenancy.TenantID
	WorkOrderID         string
	WorkflowRunID       string
	WorkflowExecutionID string
	Workflow            WorkflowDefinition
	CreatedAt           time.Time
}

// Validate rejects identifiers that cannot be safely persisted or recorded in History.
func (request StartRequest) Validate() error {
	if err := request.TenantID.Validate(); err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidStartRequest, err)
	}
	identifiers := []struct {
		name  string
		value string
	}{
		{"WorkOrder ID", request.WorkOrderID},
		{"WorkflowRun ID", request.WorkflowRunID},
		{"workflow execution ID", request.WorkflowExecutionID},
		{"workflow ID", request.Workflow.ID},
		{"workflow version", request.Workflow.Version},
		{"definition build ID", request.Workflow.DefinitionBuildID},
		{"definition digest", request.Workflow.DefinitionDigest},
	}
	for _, identifier := range identifiers {
		if err := validateStartValue(identifier.value); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrInvalidStartRequest, identifier.name, err)
		}
	}
	if !startDigestPattern.MatchString(request.Workflow.DefinitionDigest) {
		return fmt.Errorf("%w: definition digest is invalid", ErrInvalidStartRequest)
	}
	if request.CreatedAt.IsZero() || request.CreatedAt.Location() != time.UTC ||
		!request.CreatedAt.Equal(request.CreatedAt.Truncate(time.Microsecond)) {
		return fmt.Errorf("%w: created_at must use UTC PostgreSQL microsecond precision", ErrInvalidStartRequest)
	}
	return nil
}

func validateStartValue(value string) error {
	if value == "" {
		return errors.New("value is required")
	}
	if len(value) > maxStartIdentifierBytes {
		return fmt.Errorf("value exceeds %d bytes", maxStartIdentifierBytes)
	}
	if !utf8.ValidString(value) || strings.IndexByte(value, 0) >= 0 {
		return errors.New("value must be valid UTF-8 without NUL")
	}
	return nil
}

type StartOutcome string

const (
	StartCreated    StartOutcome = "created"
	StartReconciled StartOutcome = "reconciled"
)

// StartReceipt reports a confirmed native execution without exposing its Run ID.
type StartReceipt struct {
	WorkflowRunID                  string
	WorkOrderID                    string
	NativeExecutionReferenceDigest string
	Outcome                        StartOutcome
}
