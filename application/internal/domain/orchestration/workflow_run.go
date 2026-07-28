// Package orchestration defines framework-neutral durable orchestration facts.
// It does not import or expose Temporal SDK types.
package orchestration

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

const (
	maxIdentifierRunes = 200
	maxEngineRunes     = 64
)

var (
	ErrInvalidWorkflowRun    = errors.New("invalid WorkflowRun")
	ErrBindingDigestConflict = errors.New("orchestration binding digest conflict")
	ErrWorkflowRunConflict   = errors.New("WorkflowRun identity conflict")
	ErrWorkflowRunNotFound   = errors.New("WorkflowRun not found")
	ErrStartAuthority        = errors.New("WorkflowRun start authority is invalid")
)

// VersioningBehavior is the stable worker-routing behavior persisted in an
// OrchestrationBinding.
type VersioningBehavior string

const (
	VersioningPinned            VersioningBehavior = "pinned"
	VersioningCompatibleUpgrade VersioningBehavior = "compatible_upgrade"
)

// ConfirmOutcome classifies an immutable start confirmation as new or replayed.
type ConfirmOutcome string

const (
	ConfirmInserted ConfirmOutcome = "inserted"
	ConfirmReplay   ConfirmOutcome = "replay"
)

// WorkflowDefinition identifies the exact deterministic workflow definition.
type WorkflowDefinition struct {
	ID                string
	Version           string
	DefinitionBuildID string
	DefinitionDigest  string
}

// OrchestrationBinding is the stable, framework-neutral execution binding.
// Native namespace, endpoint, mutable worker identity, Run ID, and History are
// deliberately absent.
type OrchestrationBinding struct {
	EngineID                       string
	EngineVersion                  string
	WorkflowExecutionID            string
	NativeExecutionReferenceDigest string
	WorkerDeployment               string
	WorkerBuildID                  string
	VersioningBehavior             VersioningBehavior
	BindingDigest                  string
}

// WorkflowRun is the immutable PostgreSQL identity for one confirmed WorkOrder
// orchestration execution.
type WorkflowRun struct {
	WorkflowRunID        string
	TenantID             tenancy.TenantID
	WorkOrderID          string
	Workflow             WorkflowDefinition
	OrchestrationBinding OrchestrationBinding
	CreatedAt            time.Time
}

// ValidateWorkflowRunID applies the bounded identifier profile used by the
// PostgreSQL WorkflowRun repository.
func ValidateWorkflowRunID(value string) error {
	return validateIdentifier("workflow_run_id", value, maxIdentifierRunes)
}

// Validate applies the bounded Application subset of the locked WorkflowRun
// and OrchestrationBinding contracts.
func (value WorkflowRun) Validate(tenantID tenancy.TenantID) error {
	if err := tenantID.Validate(); err != nil {
		return err
	}
	if value.TenantID != tenantID {
		return ErrStartAuthority
	}
	for name, identifier := range map[string]string{
		"workflow_run_id":              value.WorkflowRunID,
		"work_order_id":                value.WorkOrderID,
		"workflow.id":                  value.Workflow.ID,
		"workflow.version":             value.Workflow.Version,
		"workflow.definition_build_id": value.Workflow.DefinitionBuildID,
	} {
		if err := validateIdentifier(name, identifier, maxIdentifierRunes); err != nil {
			return err
		}
	}
	if err := validateDigest(value.Workflow.DefinitionDigest); err != nil {
		return fmt.Errorf("%w: workflow.definition_digest", ErrInvalidWorkflowRun)
	}
	if err := value.OrchestrationBinding.Validate(); err != nil {
		return err
	}
	if value.CreatedAt.IsZero() {
		return fmt.Errorf("%w: created_at", ErrInvalidWorkflowRun)
	}
	return nil
}

// Validate verifies the closed binding shape and its RFC 8785-compatible
// SHA-256 digest.
func (value OrchestrationBinding) Validate() error {
	if err := value.validateDigestInput(); err != nil {
		return err
	}
	if err := validateDigest(value.BindingDigest); err != nil {
		return fmt.Errorf("%w: binding_digest", ErrInvalidWorkflowRun)
	}
	expected, err := value.ExpectedDigest()
	if err != nil {
		return err
	}
	if value.BindingDigest != expected {
		return ErrBindingDigestConflict
	}
	return nil
}

func (value OrchestrationBinding) validateDigestInput() error {
	for name, identifier := range map[string]struct {
		value string
		limit int
	}{
		"engine_id":             {value.EngineID, maxEngineRunes},
		"engine_version":        {value.EngineVersion, maxEngineRunes},
		"workflow_execution_id": {value.WorkflowExecutionID, maxIdentifierRunes},
		"worker_deployment":     {value.WorkerDeployment, maxIdentifierRunes},
		"worker_build_id":       {value.WorkerBuildID, maxIdentifierRunes},
	} {
		if err := validateIdentifier(name, identifier.value, identifier.limit); err != nil {
			return err
		}
	}
	if value.VersioningBehavior != VersioningPinned && value.VersioningBehavior != VersioningCompatibleUpgrade {
		return fmt.Errorf("%w: versioning_behavior", ErrInvalidWorkflowRun)
	}
	if err := validateDigest(value.NativeExecutionReferenceDigest); err != nil {
		return fmt.Errorf("%w: native_execution_reference_digest", ErrInvalidWorkflowRun)
	}
	return nil
}

// ExpectedDigest returns the RFC 8785 JCS SHA-256 digest over the binding with
// binding_digest excluded, as required by the locked Contract.
func (value OrchestrationBinding) ExpectedDigest() (string, error) {
	if err := value.validateDigestInput(); err != nil {
		return "", err
	}
	fields := map[string][]byte{
		"engine_id":                         jsonString(value.EngineID),
		"engine_version":                    jsonString(value.EngineVersion),
		"native_execution_reference_digest": jsonString(value.NativeExecutionReferenceDigest),
		"versioning_behavior":               jsonString(string(value.VersioningBehavior)),
		"worker_build_id":                   jsonString(value.WorkerBuildID),
		"worker_deployment":                 jsonString(value.WorkerDeployment),
		"workflow_execution_id":             jsonString(value.WorkflowExecutionID),
	}
	encoded, err := canonicalObject(fields)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

// DatabaseTime applies PostgreSQL's microsecond precision at the domain edge.
func DatabaseTime(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC().Truncate(time.Microsecond)
}

// Matches reports whether two values represent exactly the same immutable fact.
func (value WorkflowRun) Matches(other WorkflowRun) bool {
	return value.WorkflowRunID == other.WorkflowRunID &&
		value.TenantID == other.TenantID &&
		value.WorkOrderID == other.WorkOrderID &&
		value.Workflow == other.Workflow &&
		value.OrchestrationBinding == other.OrchestrationBinding &&
		DatabaseTime(value.CreatedAt).Equal(DatabaseTime(other.CreatedAt))
}

func validateIdentifier(name, value string, maxRunes int) error {
	if value == "" || !utf8.ValidString(value) || strings.IndexByte(value, 0) >= 0 ||
		utf8.RuneCountInString(value) > maxRunes {
		return fmt.Errorf("%w: %s", ErrInvalidWorkflowRun, name)
	}
	return nil
}

func validateDigest(value string) error {
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") || value != strings.ToLower(value) {
		return ErrInvalidWorkflowRun
	}
	decoded, err := hex.DecodeString(value[7:])
	if err != nil || len(decoded) != sha256.Size {
		return ErrInvalidWorkflowRun
	}
	return nil
}

func canonicalObject(fields map[string][]byte) ([]byte, error) {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		if !utf8.ValidString(key) {
			return nil, ErrInvalidWorkflowRun
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var builder strings.Builder
	builder.WriteByte('{')
	for index, key := range keys {
		if index > 0 {
			builder.WriteByte(',')
		}
		builder.Write(jsonString(key))
		builder.WriteByte(':')
		builder.Write(fields[key])
	}
	builder.WriteByte('}')
	return []byte(builder.String()), nil
}

func jsonString(value string) []byte {
	var builder strings.Builder
	builder.WriteByte('"')
	for _, r := range value {
		switch r {
		case '"', '\\':
			builder.WriteByte('\\')
			builder.WriteRune(r)
		case '\b':
			builder.WriteString(`\b`)
		case '\t':
			builder.WriteString(`\t`)
		case '\n':
			builder.WriteString(`\n`)
		case '\f':
			builder.WriteString(`\f`)
		case '\r':
			builder.WriteString(`\r`)
		default:
			if r < 0x20 {
				builder.WriteString(`\u00`)
				builder.WriteString(hex.EncodeToString([]byte{byte(r)}))
			} else {
				builder.WriteRune(r)
			}
		}
	}
	builder.WriteByte('"')
	return []byte(builder.String())
}
