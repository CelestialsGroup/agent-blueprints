// Package safety defines the domain values used by PostgreSQL runtime-control
// authority and ledgers. It does not own the public Wire Contract.
package safety

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

const (
	maxIdentifierRunes = 200
	MaxFanoutTargets   = 10000
	MaxClaimBatch      = 100
	MaxClaimLease      = 5 * time.Minute
)

var (
	ErrInvalidAuthority          = errors.New("invalid runtime control authority")
	ErrAuthorityConflict         = errors.New("runtime control authority conflict")
	ErrDigestConflict            = errors.New("runtime control digest conflict")
	ErrSequenceConflict          = errors.New("runtime command sequence conflict")
	ErrStaleFencing              = errors.New("runtime control fencing is stale")
	ErrInvalidControl            = errors.New("invalid runtime control")
	ErrControlNotFound           = errors.New("runtime control not found")
	ErrFanoutCoverageConflict    = errors.New("fanout target snapshot conflict")
	ErrFanoutStateRegression     = errors.New("fanout target state regression")
	ErrFanoutLeaseLost           = errors.New("fanout target lease is missing, expired, or fenced")
	ErrSafetyAuthorityUnverified = errors.New("system safety authority is not verified")
)

type Action string

const (
	ActionAppendInput           Action = "append_input"
	ActionInterrupt             Action = "interrupt"
	ActionPause                 Action = "pause"
	ActionResume                Action = "resume"
	ActionCancel                Action = "cancel"
	ActionApprovalDecision      Action = "approval_decision"
	ActionCheckpoint            Action = "checkpoint"
	ActionSubagentSpawnDecision Action = "subagent_spawn_decision"
)

type SafetyReason string

const (
	ReasonCommercialAuthorizationExpired SafetyReason = "commercial_authorization_expired"
	ReasonCommercialAuthorizationRevoked SafetyReason = "commercial_authorization_revoked"
	ReasonExecutionDeadlineExceeded      SafetyReason = "execution_deadline_exceeded"
	ReasonPolicyRevoked                  SafetyReason = "policy_revoked"
	ReasonTenantSuspended                SafetyReason = "tenant_suspended"
	ReasonProviderAdmissionRevoked       SafetyReason = "provider_admission_revoked"
	ReasonBudgetExhausted                SafetyReason = "budget_exhausted"
	ReasonReconciliationStop             SafetyReason = "reconciliation_stop"
	ReasonOperatorEmergencyStop          SafetyReason = "operator_emergency_stop"
	ReasonPlatformShutdown               SafetyReason = "platform_shutdown"
)

type WorkOrderState string

const (
	WorkOrderAccepted        WorkOrderState = "accepted"
	WorkOrderQueued          WorkOrderState = "queued"
	WorkOrderRunning         WorkOrderState = "running"
	WorkOrderWaiting         WorkOrderState = "waiting"
	WorkOrderPaused          WorkOrderState = "paused"
	WorkOrderCancelRequested WorkOrderState = "cancel_requested"
)

type RuntimeState string

const (
	RuntimeAccepted        RuntimeState = "accepted"
	RuntimeRunning         RuntimeState = "running"
	RuntimeWaitingInput    RuntimeState = "waiting_input"
	RuntimeWaitingApproval RuntimeState = "waiting_approval"
	RuntimePaused          RuntimeState = "paused"
	RuntimeCancelRequested RuntimeState = "cancel_requested"
	RuntimeOutcomeUnknown  RuntimeState = "outcome_unknown"
)

type AdmissionOutcome string

const (
	AdmissionAccepted AdmissionOutcome = "accepted"
	AdmissionRejected AdmissionOutcome = "rejected"
)

type FanoutAuthorityKind string

const (
	FanoutUserAuthority   FanoutAuthorityKind = "work_order_control_request"
	FanoutSystemAuthority FanoutAuthorityKind = "system_safety_trigger"
)

type ControlState string

const (
	ControlPending               ControlState = "pending"
	ControlDispatched            ControlState = "dispatched"
	ControlConfirmed             ControlState = "confirmed"
	ControlTerminalBeforeControl ControlState = "terminal_before_control"
	ControlOutcomeUnknown        ControlState = "outcome_unknown"
)

type AppendOutcome string

const (
	AppendInserted AppendOutcome = "inserted"
	AppendReplay   AppendOutcome = "replay"
)

type WorkOrderAuthority struct {
	TenantID           tenancy.TenantID
	WorkOrderID        string
	State              WorkOrderState
	ActiveWorkVersion  int64
	ChildAdmissionOpen bool
	CreatedAt          time.Time
}

func (value WorkOrderAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	if err := validateIdentifier("work_order_id", value.WorkOrderID); err != nil {
		return err
	}
	if !validWorkOrderState(value.State) || value.ActiveWorkVersion < 1 || value.CreatedAt.IsZero() {
		return ErrInvalidAuthority
	}
	return nil
}

type AgentRunAuthority struct {
	TenantID                       tenancy.TenantID
	WorkOrderID                    string
	AgentRunID                     string
	RunKind                        string
	RequiredForWorkOrderCompletion bool
	State                          RuntimeState
	CreatedAt                      time.Time
}

func (value AgentRunAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"work_order_id": value.WorkOrderID,
		"agent_run_id":  value.AgentRunID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if (value.RunKind != "root" && value.RunKind != "child") || !validRuntimeState(value.State) || value.CreatedAt.IsZero() {
		return ErrInvalidAuthority
	}
	return nil
}

type RuntimeRunAuthority struct {
	TenantID     tenancy.TenantID
	WorkOrderID  string
	AgentRunID   string
	RuntimeRunID string
	State        RuntimeState
	CreatedAt    time.Time
}

func (value RuntimeRunAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"work_order_id":  value.WorkOrderID,
		"agent_run_id":   value.AgentRunID,
		"runtime_run_id": value.RuntimeRunID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if !validRuntimeState(value.State) || value.CreatedAt.IsZero() {
		return ErrInvalidAuthority
	}
	return nil
}

type InvocationAuthority struct {
	TenantID            tenancy.TenantID
	WorkOrderID         string
	RuntimeRunID        string
	InvocationID        string
	RequestDigest       string
	InvocationAttemptID string
	AttemptNumber       int64
	FencingToken        int64
	InvocationCreatedAt time.Time
	AttemptCreatedAt    time.Time
}

func (value InvocationAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"work_order_id":         value.WorkOrderID,
		"runtime_run_id":        value.RuntimeRunID,
		"invocation_id":         value.InvocationID,
		"invocation_attempt_id": value.InvocationAttemptID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if err := validateDigest(value.RequestDigest); err != nil {
		return err
	}
	if value.AttemptNumber < 1 || value.FencingToken < 1 || value.InvocationCreatedAt.IsZero() ||
		value.AttemptCreatedAt.IsZero() || value.AttemptCreatedAt.Before(value.InvocationCreatedAt) {
		return ErrInvalidAuthority
	}
	return nil
}

type ControlInput struct {
	InputID        string
	InputMessageID string
	ContentDigest  string
}

type Approval struct {
	ApprovalID string
	Decision   string
	Comment    string
}

type ControlRequestAuthority struct {
	TenantID                  tenancy.TenantID
	WorkOrderID               string
	ControlRequestID          string
	RequestDigest             string
	Action                    Action
	ExpectedActiveWorkVersion int64
	Input                     *ControlInput
	Approval                  *Approval
	AcceptedAt                time.Time
}

func (value ControlRequestAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"work_order_id":      value.WorkOrderID,
		"control_request_id": value.ControlRequestID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if err := validateDigest(value.RequestDigest); err != nil {
		return err
	}
	if value.ExpectedActiveWorkVersion < 1 || value.AcceptedAt.IsZero() {
		return ErrInvalidAuthority
	}
	switch value.Action {
	case ActionAppendInput, ActionInterrupt:
		if value.Input == nil || value.Approval != nil {
			return ErrInvalidAuthority
		}
		if err := validateIdentifier("input_id", value.Input.InputID); err != nil {
			return err
		}
		if err := validateIdentifier("input_message_id", value.Input.InputMessageID); err != nil {
			return err
		}
		return validateDigest(value.Input.ContentDigest)
	case ActionApprovalDecision:
		if value.Input != nil || value.Approval == nil {
			return ErrInvalidAuthority
		}
		if err := validateIdentifier("approval_id", value.Approval.ApprovalID); err != nil {
			return err
		}
		if value.Approval.Decision != "approve" && value.Approval.Decision != "reject" {
			return ErrInvalidAuthority
		}
		if !utf8.ValidString(value.Approval.Comment) || utf8.RuneCountInString(value.Approval.Comment) > 4000 ||
			strings.IndexByte(value.Approval.Comment, 0) >= 0 {
			return ErrInvalidAuthority
		}
		return nil
	case ActionPause, ActionResume, ActionCancel:
		if value.Input != nil || value.Approval != nil {
			return ErrInvalidAuthority
		}
		return nil
	default:
		return ErrInvalidAuthority
	}
}

type ChildAdmissionAuthority struct {
	TenantID           tenancy.TenantID
	WorkOrderID        string
	DecisionID         string
	DecisionDigest     string
	SpawnRequestID     string
	SpawnRequestDigest string
	ParentAgentRunID   string
	Outcome            AdmissionOutcome
	ReasonCodes        []string
	ChildAgentRunID    string
	RuntimeRunID       string
	DecidedAt          time.Time
}

func (value ChildAdmissionAuthority) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"work_order_id":       value.WorkOrderID,
		"decision_id":         value.DecisionID,
		"spawn_request_id":    value.SpawnRequestID,
		"parent_agent_run_id": value.ParentAgentRunID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if err := validateDigest(value.DecisionDigest); err != nil {
		return err
	}
	if err := validateDigest(value.SpawnRequestDigest); err != nil {
		return err
	}
	if value.DecidedAt.IsZero() {
		return ErrInvalidAuthority
	}
	if err := validateAdmissionReasonCodes(value.Outcome, value.ReasonCodes); err != nil {
		return err
	}
	switch value.Outcome {
	case AdmissionAccepted:
		if err := validateIdentifier("child_agent_run_id", value.ChildAgentRunID); err != nil {
			return err
		}
		return validateIdentifier("runtime_run_id", value.RuntimeRunID)
	case AdmissionRejected:
		if value.ChildAgentRunID != "" || value.RuntimeRunID != "" {
			return ErrInvalidAuthority
		}
		return nil
	default:
		return ErrInvalidAuthority
	}
}

type SystemSafetyControl struct {
	SafetyControlID    string
	TenantID           tenancy.TenantID
	WorkOrderID        string
	RuntimeRunID       string
	Action             Action
	Reason             SafetyReason
	EvidenceContractID string
	EvidenceID         string
	EvidenceDigest     string
	ObservedAt         time.Time
	IssuerSubjectID    string
	IssuedAt           time.Time
	ControlDigest      string
}

func (value SystemSafetyControl) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"safety_control_id":    value.SafetyControlID,
		"work_order_id":        value.WorkOrderID,
		"runtime_run_id":       value.RuntimeRunID,
		"evidence_contract_id": value.EvidenceContractID,
		"evidence_id":          value.EvidenceID,
		"issuer_subject_id":    value.IssuerSubjectID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if !validContractID(value.EvidenceContractID) || !validSafetyAction(value.Action) || !validSafetyReason(value.Reason) {
		return ErrInvalidControl
	}
	if hardCancelReason(value.Reason) && value.Action != ActionCancel {
		return ErrInvalidControl
	}
	if value.ObservedAt.IsZero() || value.IssuedAt.IsZero() || value.ObservedAt.After(value.IssuedAt) {
		return ErrInvalidControl
	}
	if err := validateDigest(value.EvidenceDigest); err != nil {
		return err
	}
	expected, err := value.ExpectedDigest()
	if err != nil {
		return err
	}
	if value.ControlDigest != expected {
		return fmt.Errorf("%w: system safety control", ErrDigestConflict)
	}
	return nil
}

func (value SystemSafetyControl) ExpectedDigest() (string, error) {
	encoded, err := value.canonical(false)
	if err != nil {
		return "", err
	}
	return sha256Digest(encoded), nil
}

func (value SystemSafetyControl) Payload() ([]byte, error) {
	return value.canonical(true)
}

func (value SystemSafetyControl) canonical(includeDigest bool) ([]byte, error) {
	evidence, err := canonicalObject(map[string][]byte{
		"evidence_contract_id": jsonString(value.EvidenceContractID),
		"evidence_digest":      jsonString(value.EvidenceDigest),
		"evidence_id":          jsonString(value.EvidenceID),
		"observed_at":          jsonString(formatTime(value.ObservedAt)),
	})
	if err != nil {
		return nil, err
	}
	fields := map[string][]byte{
		"action":            jsonString(string(value.Action)),
		"issued_at":         jsonString(formatTime(value.IssuedAt)),
		"issued_by":         jsonString("platform_safety_controller"),
		"issuer_subject_id": jsonString(value.IssuerSubjectID),
		"reason":            jsonString(string(value.Reason)),
		"runtime_run_id":    jsonString(value.RuntimeRunID),
		"safety_control_id": jsonString(value.SafetyControlID),
		"tenant_id":         jsonString(string(value.TenantID)),
		"trigger_evidence":  evidence,
		"work_order_id":     jsonString(value.WorkOrderID),
	}
	if includeDigest {
		fields["control_digest"] = jsonString(value.ControlDigest)
	}
	return canonicalObject(fields)
}

type RuntimeCommand struct {
	CommandID                    string
	CommandDigest                string
	WorkOrderID                  string
	RuntimeRunID                 string
	CommandSequence              int64
	Type                         Action
	AuthorizedControlRequestID   string
	SystemSafetyControlID        string
	SystemSafetyControlDigest    string
	InputID                      string
	InputContentDigest           string
	Approval                     *Approval
	SpawnRequestID               string
	ChildAdmissionDecisionID     string
	ChildAdmissionDecisionDigest string
	SpawnOutcome                 AdmissionOutcome
	SpawnReasonCodes             []string
	ChildAgentRunID              string
	Reason                       string
	InvocationID                 string
	InvocationAttemptID          string
	FencingToken                 int64
	IdempotencyKey               string
	DeadlineAt                   time.Time
	CreatedAt                    time.Time
}

func (value RuntimeCommand) Validate() error {
	for name, id := range map[string]string{
		"command_id":            value.CommandID,
		"work_order_id":         value.WorkOrderID,
		"runtime_run_id":        value.RuntimeRunID,
		"invocation_id":         value.InvocationID,
		"invocation_attempt_id": value.InvocationAttemptID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if value.CommandSequence < 1 || value.FencingToken < 1 || utf8.RuneCountInString(value.IdempotencyKey) < 16 {
		return ErrInvalidControl
	}
	if err := validateIdentifier("idempotency_key", value.IdempotencyKey); err != nil {
		return err
	}
	if value.CreatedAt.IsZero() || value.DeadlineAt.IsZero() ||
		!DatabaseTime(value.DeadlineAt).After(DatabaseTime(value.CreatedAt)) {
		return ErrInvalidControl
	}
	if err := value.validateShape(); err != nil {
		return err
	}
	expected, err := value.ExpectedDigest()
	if err != nil {
		return err
	}
	if value.CommandDigest != expected {
		return fmt.Errorf("%w: runtime command", ErrDigestConflict)
	}
	return nil
}

func (value RuntimeCommand) validateShape() error {
	for name, id := range map[string]string{
		"authorized_control_request_id":         value.AuthorizedControlRequestID,
		"system_safety_control_id":              value.SystemSafetyControlID,
		"input_id":                              value.InputID,
		"spawn_request_id":                      value.SpawnRequestID,
		"child_agent_run_admission_decision_id": value.ChildAdmissionDecisionID,
		"child_agent_run_id":                    value.ChildAgentRunID,
	} {
		if err := validateOptionalIdentifier(name, id); err != nil {
			return err
		}
	}
	user := value.AuthorizedControlRequestID != ""
	system := value.SystemSafetyControlID != "" || value.SystemSafetyControlDigest != ""
	child := value.ChildAdmissionDecisionID != ""
	switch value.Type {
	case ActionAppendInput, ActionInterrupt:
		if !user || system || child || value.InputID == "" || value.InputContentDigest == "" || value.Approval != nil {
			return ErrInvalidControl
		}
		if err := validateDigest(value.InputContentDigest); err != nil {
			return err
		}
	case ActionApprovalDecision:
		if !user || system || child || value.Approval == nil || value.InputID != "" || value.InputContentDigest != "" {
			return ErrInvalidControl
		}
		if value.Approval.Decision != "approve" && value.Approval.Decision != "reject" {
			return ErrInvalidControl
		}
		if err := validateIdentifier("approval_id", value.Approval.ApprovalID); err != nil {
			return err
		}
		if !utf8.ValidString(value.Approval.Comment) || utf8.RuneCountInString(value.Approval.Comment) > 4000 ||
			strings.IndexByte(value.Approval.Comment, 0) >= 0 {
			return ErrInvalidControl
		}
	case ActionPause, ActionCancel:
		if user == system || child || value.InputID != "" || value.Approval != nil {
			return ErrInvalidControl
		}
		if system {
			if err := validateDigest(value.SystemSafetyControlDigest); err != nil {
				return err
			}
		}
	case ActionResume:
		if !user || system || child || value.InputID != "" || value.Approval != nil {
			return ErrInvalidControl
		}
	case ActionCheckpoint:
		if user || system || child || value.InputID != "" || value.Approval != nil {
			return ErrInvalidControl
		}
	case ActionSubagentSpawnDecision:
		if user || system || !child || value.SpawnRequestID == "" || value.SpawnOutcome == "" || len(value.SpawnReasonCodes) == 0 || len(value.SpawnReasonCodes) > 16 {
			return ErrInvalidControl
		}
		if err := validateDigest(value.ChildAdmissionDecisionDigest); err != nil {
			return err
		}
		if value.SpawnOutcome == AdmissionAccepted && value.ChildAgentRunID == "" {
			return ErrInvalidControl
		}
		if value.SpawnOutcome == AdmissionRejected && value.ChildAgentRunID != "" {
			return ErrInvalidControl
		}
		if err := validateAdmissionReasonCodes(value.SpawnOutcome, value.SpawnReasonCodes); err != nil {
			return err
		}
	default:
		return ErrInvalidControl
	}
	if !utf8.ValidString(value.Reason) || utf8.RuneCountInString(value.Reason) > 1000 ||
		strings.IndexByte(value.Reason, 0) >= 0 {
		return ErrInvalidControl
	}
	return nil
}

func (value RuntimeCommand) ExpectedDigest() (string, error) {
	encoded, err := value.canonical(false)
	if err != nil {
		return "", err
	}
	return sha256Digest(encoded), nil
}

func (value RuntimeCommand) Payload() ([]byte, error) {
	return value.canonical(true)
}

func (value RuntimeCommand) canonical(includeDigest bool) ([]byte, error) {
	fields := map[string][]byte{
		"command_id":            jsonString(value.CommandID),
		"command_sequence":      []byte(strconv.FormatInt(value.CommandSequence, 10)),
		"deadline_at":           jsonString(formatTime(value.DeadlineAt)),
		"fencing_token":         []byte(strconv.FormatInt(value.FencingToken, 10)),
		"idempotency_key":       jsonString(value.IdempotencyKey),
		"invocation_attempt_id": jsonString(value.InvocationAttemptID),
		"invocation_id":         jsonString(value.InvocationID),
		"runtime_run_id":        jsonString(value.RuntimeRunID),
		"type":                  jsonString(string(value.Type)),
	}
	optionalString(fields, "authorized_control_request_id", value.AuthorizedControlRequestID)
	optionalString(fields, "system_safety_control_id", value.SystemSafetyControlID)
	optionalString(fields, "system_safety_control_digest", value.SystemSafetyControlDigest)
	optionalString(fields, "input_id", value.InputID)
	optionalString(fields, "input_content_digest", value.InputContentDigest)
	optionalString(fields, "spawn_request_id", value.SpawnRequestID)
	optionalString(fields, "child_agent_run_admission_decision_id", value.ChildAdmissionDecisionID)
	optionalString(fields, "child_agent_run_admission_decision_digest", value.ChildAdmissionDecisionDigest)
	optionalString(fields, "spawn_outcome", string(value.SpawnOutcome))
	optionalString(fields, "child_agent_run_id", value.ChildAgentRunID)
	optionalString(fields, "reason", value.Reason)
	if value.Approval != nil {
		fields["approval_id"] = jsonString(value.Approval.ApprovalID)
		decision := map[string][]byte{"decision": jsonString(value.Approval.Decision)}
		optionalString(decision, "comment", value.Approval.Comment)
		encoded, err := canonicalObject(decision)
		if err != nil {
			return nil, err
		}
		fields["decision"] = encoded
	}
	if len(value.SpawnReasonCodes) > 0 {
		items := make([][]byte, 0, len(value.SpawnReasonCodes))
		for _, code := range value.SpawnReasonCodes {
			items = append(items, jsonString(code))
		}
		fields["spawn_reason_codes"] = canonicalArray(items)
	}
	if includeDigest {
		fields["command_digest"] = jsonString(value.CommandDigest)
	}
	return canonicalObject(fields)
}

type FanoutTarget struct {
	AgentRunID                string
	RuntimeRunID              string
	TargetFencingToken        int64
	SystemSafetyControlID     string
	SystemSafetyControlDigest string
	CommandID                 string
	ControlState              ControlState
}

type FanoutSnapshot struct {
	FanoutID                 string
	FanoutVersion            int64
	PreviousFanoutDigest     string
	FanoutDigest             string
	TenantID                 tenancy.TenantID
	WorkOrderID              string
	Action                   Action
	AuthorityKind            FanoutAuthorityKind
	AuthorityID              string
	AuthorityDigest          string
	SafetyEvidenceContractID string
	Targets                  []FanoutTarget
	CreatedAt                time.Time
	UpdatedAt                time.Time
}

func (value FanoutSnapshot) Validate(tenantID tenancy.TenantID) error {
	if err := sameTenant(tenantID, value.TenantID); err != nil {
		return err
	}
	for name, id := range map[string]string{
		"fanout_id":     value.FanoutID,
		"work_order_id": value.WorkOrderID,
		"authority_id":  value.AuthorityID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if !validSafetyAction(value.Action) || value.FanoutVersion < 1 || len(value.Targets) > MaxFanoutTargets {
		return ErrInvalidControl
	}
	if value.FanoutVersion == 1 && value.PreviousFanoutDigest != "" || value.FanoutVersion > 1 && value.PreviousFanoutDigest == "" {
		return ErrInvalidControl
	}
	if value.PreviousFanoutDigest != "" {
		if err := validateDigest(value.PreviousFanoutDigest); err != nil {
			return err
		}
	}
	if err := validateDigest(value.AuthorityDigest); err != nil {
		return err
	}
	if value.CreatedAt.IsZero() || value.UpdatedAt.IsZero() || value.UpdatedAt.Before(value.CreatedAt) {
		return ErrInvalidControl
	}
	seenAgents := map[string]struct{}{}
	seenRuntime := map[string]struct{}{}
	for _, target := range value.Targets {
		if err := validateIdentifier("agent_run_id", target.AgentRunID); err != nil {
			return err
		}
		if err := validateIdentifier("runtime_run_id", target.RuntimeRunID); err != nil {
			return err
		}
		if err := validateIdentifier("command_id", target.CommandID); err != nil {
			return err
		}
		if target.TargetFencingToken < 1 || !validControlState(target.ControlState) {
			return ErrInvalidControl
		}
		if _, exists := seenAgents[target.AgentRunID]; exists {
			return ErrFanoutCoverageConflict
		}
		if _, exists := seenRuntime[target.RuntimeRunID]; exists {
			return ErrFanoutCoverageConflict
		}
		seenAgents[target.AgentRunID] = struct{}{}
		seenRuntime[target.RuntimeRunID] = struct{}{}
		systemPair := target.SystemSafetyControlID != "" || target.SystemSafetyControlDigest != ""
		if value.AuthorityKind == FanoutSystemAuthority {
			if !systemPair || target.SystemSafetyControlID == "" || target.SystemSafetyControlDigest == "" {
				return ErrInvalidControl
			}
			if err := validateIdentifier("system_safety_control_id", target.SystemSafetyControlID); err != nil {
				return err
			}
			if err := validateDigest(target.SystemSafetyControlDigest); err != nil {
				return err
			}
		} else if systemPair {
			return ErrInvalidControl
		}
	}
	if value.AuthorityKind == FanoutSystemAuthority {
		if err := validateIdentifier("safety_evidence_contract_id", value.SafetyEvidenceContractID); err != nil {
			return err
		}
		if !validContractID(value.SafetyEvidenceContractID) {
			return ErrInvalidControl
		}
	} else if value.AuthorityKind != FanoutUserAuthority || value.SafetyEvidenceContractID != "" {
		return ErrInvalidControl
	}
	expected, err := value.ExpectedDigest()
	if err != nil {
		return err
	}
	if value.FanoutDigest != expected {
		return fmt.Errorf("%w: fanout snapshot", ErrDigestConflict)
	}
	return nil
}

func (value FanoutSnapshot) ExpectedDigest() (string, error) {
	encoded, err := value.canonical(false)
	if err != nil {
		return "", err
	}
	return sha256Digest(encoded), nil
}

func (value FanoutSnapshot) Payload() ([]byte, error) {
	return value.canonical(true)
}

func (value FanoutSnapshot) canonical(includeDigest bool) ([]byte, error) {
	targets := append([]FanoutTarget(nil), value.Targets...)
	sort.Slice(targets, func(i, j int) bool {
		if targets[i].AgentRunID == targets[j].AgentRunID {
			return targets[i].RuntimeRunID < targets[j].RuntimeRunID
		}
		return targets[i].AgentRunID < targets[j].AgentRunID
	})
	items := make([][]byte, 0, len(targets))
	for _, target := range targets {
		fields := map[string][]byte{
			"agent_run_id":         jsonString(target.AgentRunID),
			"control_state":        jsonString(string(target.ControlState)),
			"runtime_run_id":       jsonString(target.RuntimeRunID),
			"target_fencing_token": []byte(strconv.FormatInt(target.TargetFencingToken, 10)),
		}
		optionalString(fields, "system_safety_control_id", target.SystemSafetyControlID)
		optionalString(fields, "system_safety_control_digest", target.SystemSafetyControlDigest)
		encoded, err := canonicalObject(fields)
		if err != nil {
			return nil, err
		}
		items = append(items, encoded)
	}
	previous := []byte("null")
	if value.PreviousFanoutDigest != "" {
		previous = jsonString(value.PreviousFanoutDigest)
	}
	fields := map[string][]byte{
		"action":                 jsonString(string(value.Action)),
		"authority_digest":       jsonString(value.AuthorityDigest),
		"authority_id":           jsonString(value.AuthorityID),
		"authority_kind":         jsonString(string(value.AuthorityKind)),
		"created_at":             jsonString(formatTime(value.CreatedAt)),
		"fanout_id":              jsonString(value.FanoutID),
		"fanout_version":         []byte(strconv.FormatInt(value.FanoutVersion, 10)),
		"previous_fanout_digest": previous,
		"targets":                canonicalArray(items),
		"tenant_id":              jsonString(string(value.TenantID)),
		"updated_at":             jsonString(formatTime(value.UpdatedAt)),
		"work_order_id":          jsonString(value.WorkOrderID),
	}
	if includeDigest {
		fields["fanout_digest"] = jsonString(value.FanoutDigest)
	}
	return canonicalObject(fields)
}

type FanoutClaimRequest struct {
	WorkerID      string
	BatchSize     int32
	LeaseDuration time.Duration
}

func (value FanoutClaimRequest) Validate() error {
	if err := validateIdentifier("worker_id", value.WorkerID); err != nil {
		return err
	}
	if value.BatchSize < 1 || value.BatchSize > MaxClaimBatch || value.LeaseDuration <= 0 || value.LeaseDuration > MaxClaimLease || value.LeaseDuration%time.Microsecond != 0 {
		return ErrInvalidControl
	}
	return nil
}

type FanoutLease struct {
	FanoutID          string
	AgentRunID        string
	WorkerID          string
	ClaimFencingToken int64
}

func (value FanoutLease) Validate() error {
	for name, id := range map[string]string{
		"fanout_id":    value.FanoutID,
		"agent_run_id": value.AgentRunID,
		"worker_id":    value.WorkerID,
	} {
		if err := validateIdentifier(name, id); err != nil {
			return err
		}
	}
	if value.ClaimFencingToken < 1 {
		return ErrInvalidControl
	}
	return nil
}

func ValidateFanoutID(value string) error {
	return validateIdentifier("fanout_id", value)
}

type ClaimedFanoutTarget struct {
	TenantID                  tenancy.TenantID
	WorkOrderID               string
	FanoutID                  string
	AgentRunID                string
	RuntimeRunID              string
	TargetFencingToken        int64
	SystemSafetyControlID     string
	SystemSafetyControlDigest string
	CommandID                 string
	ControlState              ControlState
	ClaimFencingToken         int64
	WorkerID                  string
	LeaseExpiresAt            time.Time
}

func (value ClaimedFanoutTarget) Lease() FanoutLease {
	return FanoutLease{
		FanoutID:          value.FanoutID,
		AgentRunID:        value.AgentRunID,
		WorkerID:          value.WorkerID,
		ClaimFencingToken: value.ClaimFencingToken,
	}
}

func CanProgress(from, to ControlState) bool {
	if from == to {
		return true
	}
	switch from {
	case ControlPending:
		return to == ControlDispatched || to == ControlOutcomeUnknown || to == ControlConfirmed || to == ControlTerminalBeforeControl
	case ControlDispatched:
		return to == ControlOutcomeUnknown || to == ControlConfirmed || to == ControlTerminalBeforeControl
	case ControlOutcomeUnknown:
		return to == ControlConfirmed || to == ControlTerminalBeforeControl
	default:
		return false
	}
}

func DatabaseTime(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC().Truncate(time.Microsecond)
}

func validateAdmissionReasonCodes(outcome AdmissionOutcome, codes []string) error {
	if len(codes) < 1 || len(codes) > 16 {
		return ErrInvalidAuthority
	}
	seen := make(map[string]struct{}, len(codes))
	for _, code := range codes {
		if !validAdmissionReasonCode(code) {
			return ErrInvalidAuthority
		}
		if _, exists := seen[code]; exists {
			return ErrInvalidAuthority
		}
		seen[code] = struct{}{}
	}
	_, admitted := seen["admitted"]
	if outcome == AdmissionAccepted && (len(codes) != 1 || !admitted) {
		return ErrInvalidAuthority
	}
	if outcome == AdmissionRejected && admitted {
		return ErrInvalidAuthority
	}
	return nil
}

func validAdmissionReasonCode(value string) bool {
	switch value {
	case "admitted", "work_order_not_active", "depth_limit", "run_count_limit",
		"parallel_limit", "budget_unavailable", "policy_denied",
		"capability_unavailable", "provider_unavailable", "sandbox_unavailable",
		"workspace_conflict":
		return true
	default:
		return false
	}
}

func validWorkOrderState(value WorkOrderState) bool {
	switch value {
	case WorkOrderAccepted, WorkOrderQueued, WorkOrderRunning, WorkOrderWaiting, WorkOrderPaused, WorkOrderCancelRequested:
		return true
	default:
		return false
	}
}

func validRuntimeState(value RuntimeState) bool {
	switch value {
	case RuntimeAccepted, RuntimeRunning, RuntimeWaitingInput, RuntimeWaitingApproval, RuntimePaused, RuntimeCancelRequested, RuntimeOutcomeUnknown:
		return true
	default:
		return false
	}
}

func validSafetyAction(value Action) bool {
	return value == ActionPause || value == ActionCancel
}

func validControlState(value ControlState) bool {
	switch value {
	case ControlPending, ControlDispatched, ControlConfirmed, ControlTerminalBeforeControl, ControlOutcomeUnknown:
		return true
	default:
		return false
	}
}

func validSafetyReason(value SafetyReason) bool {
	switch value {
	case ReasonCommercialAuthorizationExpired, ReasonCommercialAuthorizationRevoked,
		ReasonExecutionDeadlineExceeded, ReasonPolicyRevoked, ReasonTenantSuspended,
		ReasonProviderAdmissionRevoked, ReasonBudgetExhausted, ReasonReconciliationStop,
		ReasonOperatorEmergencyStop, ReasonPlatformShutdown:
		return true
	default:
		return false
	}
}

func hardCancelReason(value SafetyReason) bool {
	switch value {
	case ReasonCommercialAuthorizationExpired, ReasonCommercialAuthorizationRevoked,
		ReasonExecutionDeadlineExceeded, ReasonPolicyRevoked, ReasonTenantSuspended,
		ReasonProviderAdmissionRevoked, ReasonBudgetExhausted, ReasonPlatformShutdown:
		return true
	default:
		return false
	}
}

func sameTenant(expected, actual tenancy.TenantID) error {
	if err := expected.Validate(); err != nil {
		return err
	}
	if err := actual.Validate(); err != nil {
		return err
	}
	if expected != actual {
		return ErrInvalidAuthority
	}
	return nil
}

func validateIdentifier(name, value string) error {
	if value == "" || !utf8.ValidString(value) || utf8.RuneCountInString(value) > maxIdentifierRunes || strings.IndexByte(value, 0) >= 0 {
		return fmt.Errorf("%w: %s", ErrInvalidAuthority, name)
	}
	return nil
}

func validateOptionalIdentifier(name, value string) error {
	if value == "" {
		return nil
	}
	return validateIdentifier(name, value)
}

func validateDigest(value string) error {
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") {
		return ErrInvalidAuthority
	}
	decoded, err := hex.DecodeString(value[7:])
	if err != nil || len(decoded) != sha256.Size || value != strings.ToLower(value) {
		return ErrInvalidAuthority
	}
	return nil
}

func validContractID(value string) bool {
	if !strings.HasPrefix(value, "urn:agent-platform:") {
		return false
	}
	remainder := strings.TrimPrefix(value, "urn:agent-platform:")
	name, version, ok := strings.Cut(remainder, ":v")
	if !ok || name == "" || version == "" {
		return false
	}
	for _, r := range name {
		if (r < 'a' || r > 'z') && (r < '0' || r > '9') && r != '-' {
			return false
		}
	}
	for _, r := range version {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

func sha256Digest(encoded []byte) string {
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func formatTime(value time.Time) string {
	return DatabaseTime(value).Format(time.RFC3339Nano)
}

func optionalString(fields map[string][]byte, key, value string) {
	if value != "" {
		fields[key] = jsonString(value)
	}
}

func canonicalObject(fields map[string][]byte) ([]byte, error) {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		if !utf8.ValidString(key) {
			return nil, ErrInvalidControl
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

func canonicalArray(items [][]byte) []byte {
	var builder strings.Builder
	builder.WriteByte('[')
	for index, item := range items {
		if index > 0 {
			builder.WriteByte(',')
		}
		builder.Write(item)
	}
	builder.WriteByte(']')
	return []byte(builder.String())
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
