package persistence

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"slices"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
	"github.com/shell-echo/agent/internal/messaging"
	"github.com/shell-echo/agent/internal/safety"
)

type RuntimeControlAuthorities struct {
	WorkOrders      []safety.WorkOrderAuthority
	AgentRuns       []safety.AgentRunAuthority
	RuntimeRuns     []safety.RuntimeRunAuthority
	Invocations     []safety.InvocationAuthority
	ControlRequests []safety.ControlRequestAuthority
	ChildAdmissions []safety.ChildAdmissionAuthority
}

const (
	// MaxRuntimeControlAuthorityBatch bounds one admission transaction.
	MaxRuntimeControlAuthorityBatch = 10000
	runtimeControlOutboxDestination = "agent-runtime-control"
)

// SystemSafetyAuthorityVerifier is implemented by the authenticated control
// plane. It binds the current WorkloadIdentity and the reason/evidence profile.
// Verification must be side-effect free and runs before the repository opens a
// database transaction.
type SystemSafetyAuthorityVerifier interface {
	VerifySystemSafetyAuthority(context.Context, tenancy.TenantID, safety.SystemSafetyControl) error
}

// RuntimeControlRepositoryOption configures trusted repository boundaries.
type RuntimeControlRepositoryOption func(*RuntimeControlRepository) error

// WithSystemSafetyAuthorityVerifier enables verified system safety writes.
func WithSystemSafetyAuthorityVerifier(verifier SystemSafetyAuthorityVerifier) RuntimeControlRepositoryOption {
	return func(repository *RuntimeControlRepository) error {
		if verifier == nil {
			return errors.New("system safety authority verifier is required")
		}
		if repository.safetyAuthorityVerifier != nil {
			return errors.New("system safety authority verifier is already configured")
		}
		repository.safetyAuthorityVerifier = verifier
		return nil
	}
}

type RuntimeControlRepository struct {
	runner                  *TransactionRunner
	safetyAuthorityVerifier SystemSafetyAuthorityVerifier
}

func NewRuntimeControlRepository(
	runner *TransactionRunner,
	options ...RuntimeControlRepositoryOption,
) (*RuntimeControlRepository, error) {
	if runner == nil {
		return nil, errors.New("transaction runner is required")
	}
	repository := &RuntimeControlRepository{runner: runner}
	for _, option := range options {
		if option == nil {
			return nil, errors.New("runtime control repository option is required")
		}
		if err := option(repository); err != nil {
			return nil, err
		}
	}
	return repository, nil
}

func (repository *RuntimeControlRepository) AdmitAuthorities(
	ctx context.Context,
	tenantID tenancy.TenantID,
	authorities RuntimeControlAuthorities,
) error {
	var err error
	authorities, err = normalizeRuntimeControlAuthorities(authorities)
	if err != nil {
		return err
	}
	if err := validateRuntimeControlAuthorities(tenantID, authorities); err != nil {
		return err
	}
	return repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		for _, authority := range authorities.WorkOrders {
			if err := admitWorkOrder(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		if err := lockAuthorityWorkOrders(ctx, txRepository, tenantID, authorities); err != nil {
			return err
		}
		for _, authority := range authorities.AgentRuns {
			if err := admitAgentRun(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		for _, authority := range authorities.RuntimeRuns {
			if err := admitRuntimeRun(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		for _, authority := range authorities.Invocations {
			if err := admitInvocation(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		for _, authority := range authorities.ControlRequests {
			if err := admitControlRequest(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		for _, authority := range authorities.ChildAdmissions {
			if err := admitChildAdmission(ctx, txRepository, tenantID, authority); err != nil {
				return err
			}
		}
		return nil
	})
}

func (repository *RuntimeControlRepository) AppendSystemSafetyControl(
	ctx context.Context,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
	outboxMessage messaging.OutboundMessage,
) (safety.AppendOutcome, error) {
	if err := repository.verifySystemSafetyAuthority(ctx, tenantID, control); err != nil {
		return "", err
	}
	var outcome safety.AppendOutcome
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		var err error
		outcome, err = appendSystemSafetyControl(ctx, txRepository, tenantID, control, outboxMessage)
		return err
	})
	return outcome, err
}

func (repository *RuntimeControlRepository) AppendRuntimeCommand(
	ctx context.Context,
	tenantID tenancy.TenantID,
	command safety.RuntimeCommand,
	outboxMessage messaging.OutboundMessage,
) (safety.AppendOutcome, error) {
	var outcome safety.AppendOutcome
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		var err error
		outcome, err = appendRuntimeCommand(ctx, txRepository, tenantID, command, outboxMessage)
		return err
	})
	return outcome, err
}

func appendSystemSafetyControl(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
	outboxMessage messaging.OutboundMessage,
) (safety.AppendOutcome, error) {
	if err := repository.requireTransaction(ctx); err != nil {
		return "", err
	}
	if err := control.Validate(tenantID); err != nil {
		return "", err
	}
	if err := validateSafetyControlOutbox(control, outboxMessage); err != nil {
		return "", err
	}

	runtimeRun, err := repository.queries.GetAgentRuntimeRunAuthority(ctx, agentdb.GetAgentRuntimeRunAuthorityParams{
		TenantID: string(tenantID), RuntimeRunID: control.RuntimeRunID,
	})
	if err != nil {
		return "", classifyAuthorityRead("read safety-control RuntimeRun", err)
	}
	if runtimeRun.WorkOrderID != control.WorkOrderID {
		return "", safety.ErrInvalidAuthority
	}
	controller, err := repository.queries.GetPlatformSafetyControllerAuthority(
		ctx,
		agentdb.GetPlatformSafetyControllerAuthorityParams{
			TenantID: string(tenantID), IssuerSubjectID: control.IssuerSubjectID,
		},
	)
	if err != nil {
		return "", classifyAuthorityRead("read Safety Controller authority", err)
	}
	evidence, err := repository.queries.GetSafetyTriggerEvidenceAuthority(
		ctx,
		agentdb.GetSafetyTriggerEvidenceAuthorityParams{
			TenantID: string(tenantID), EvidenceContractID: control.EvidenceContractID,
			EvidenceID: control.EvidenceID,
		},
	)
	if err != nil {
		return "", classifyAuthorityRead("read safety trigger evidence", err)
	}
	if evidence.WorkOrderID != control.WorkOrderID || evidence.EvidenceDigest != control.EvidenceDigest ||
		evidence.Action != string(control.Action) || evidence.Reason != string(control.Reason) ||
		!evidence.ObservedAt.Time.Equal(safety.DatabaseTime(control.ObservedAt)) ||
		evidence.AdmittedAt.Time.After(safety.DatabaseTime(control.IssuedAt)) ||
		controller.AdmittedAt.Time.After(safety.DatabaseTime(control.IssuedAt)) {
		return "", safety.ErrInvalidAuthority
	}

	_, err = repository.queries.InsertSystemSafetyControl(ctx, agentdb.InsertSystemSafetyControlParams{
		TenantID: string(tenantID), WorkOrderID: control.WorkOrderID,
		RuntimeRunID: control.RuntimeRunID, SafetyControlID: control.SafetyControlID,
		Action: string(control.Action), Reason: string(control.Reason),
		EvidenceContractID: control.EvidenceContractID, EvidenceID: control.EvidenceID,
		EvidenceDigest: control.EvidenceDigest, ObservedAt: timestamp(control.ObservedAt),
		EvidenceAdmittedAt: evidence.AdmittedAt, IssuedBy: "platform_safety_controller",
		IssuerSubjectID: control.IssuerSubjectID, IssuerAdmittedAt: controller.AdmittedAt,
		IssuedAt: timestamp(control.IssuedAt), ControlDigest: control.ControlDigest,
		OutboxMessageID: outboxMessage.MessageID, OutboxPayloadDigest: outboxMessage.PayloadDigest,
		OutboxDestination: outboxMessage.Destination, OutboxAvailableAt: timestamp(outboxMessage.AvailableAt),
		OutboxCreatedAt: timestamp(outboxMessage.CreatedAt),
	})
	outcome := safety.AppendInserted
	if errors.Is(err, pgx.ErrNoRows) {
		existing, readErr := repository.queries.GetSystemSafetyControl(
			ctx,
			agentdb.GetSystemSafetyControlParams{TenantID: string(tenantID), SafetyControlID: control.SafetyControlID},
		)
		if errors.Is(readErr, pgx.ErrNoRows) {
			return "", safety.ErrDigestConflict
		}
		if readErr != nil {
			return "", fmt.Errorf("read conflicting SystemSafetyControl: %w", readErr)
		}
		if existing.ControlDigest != control.ControlDigest {
			return "", safety.ErrDigestConflict
		}
		if existing.OutboxMessageID != outboxMessage.MessageID ||
			existing.OutboxPayloadDigest != outboxMessage.PayloadDigest {
			return "", messaging.ErrOutboxConflict
		}
		outcome = safety.AppendReplay
	} else if err != nil {
		return "", classifyControlWrite("append SystemSafetyControl", err)
	}
	if outcome == safety.AppendInserted && isTerminalRuntimeState(runtimeRun.State) {
		return "", safety.ErrInvalidAuthority
	}
	if _, err := repository.EnqueueOutboxMessage(ctx, outboxMessage); err != nil {
		return "", err
	}
	return outcome, nil
}

func appendRuntimeCommand(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	command safety.RuntimeCommand,
	outboxMessage messaging.OutboundMessage,
) (safety.AppendOutcome, error) {
	if err := repository.requireTransaction(ctx); err != nil {
		return "", err
	}
	if err := command.Validate(); err != nil {
		return "", err
	}
	if err := validateRuntimeCommandOutbox(command, outboxMessage); err != nil {
		return "", err
	}
	runtimeRun, err := repository.queries.LockRuntimeRunForCommand(ctx, agentdb.LockRuntimeRunForCommandParams{
		TenantID: string(tenantID), RuntimeRunID: command.RuntimeRunID,
	})
	if err != nil {
		return "", classifyAuthorityRead("lock command RuntimeRun", err)
	}
	if runtimeRun.WorkOrderID != command.WorkOrderID {
		return "", safety.ErrInvalidAuthority
	}

	existing, err := repository.queries.GetAgentRuntimeCommand(ctx, agentdb.GetAgentRuntimeCommandParams{
		TenantID: string(tenantID), CommandID: command.CommandID,
	})
	if err == nil {
		if existing.CommandDigest != command.CommandDigest {
			return "", safety.ErrDigestConflict
		}
		if existing.OutboxMessageID != outboxMessage.MessageID ||
			existing.OutboxPayloadDigest != outboxMessage.PayloadDigest {
			return "", messaging.ErrOutboxConflict
		}
		if _, err := repository.EnqueueOutboxMessage(ctx, outboxMessage); err != nil {
			return "", err
		}
		return safety.AppendReplay, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return "", fmt.Errorf("read runtime command identity: %w", err)
	}
	if isTerminalRuntimeState(runtimeRun.State) {
		return "", safety.ErrInvalidAuthority
	}
	if command.CommandSequence != runtimeRun.LastCommandSequence+1 {
		return "", safety.ErrSequenceConflict
	}
	if command.FencingToken <= runtimeRun.CurrentFencingToken {
		return "", safety.ErrStaleFencing
	}

	params := runtimeCommandParams(tenantID, command, outboxMessage)
	if _, err := repository.queries.InsertAgentRuntimeCommand(ctx, params); errors.Is(err, pgx.ErrNoRows) {
		return "", safety.ErrDigestConflict
	} else if err != nil {
		return "", classifyControlWrite("append AgentRuntimeCommand", err)
	}
	if _, err := repository.queries.AdvanceRuntimeCommandCursor(ctx, agentdb.AdvanceRuntimeCommandCursorParams{
		CommandSequence: command.CommandSequence, FencingToken: command.FencingToken,
		UpdatedAt: timestamp(command.CreatedAt), TenantID: string(tenantID), RuntimeRunID: command.RuntimeRunID,
	}); errors.Is(err, pgx.ErrNoRows) {
		return "", safety.ErrStaleFencing
	} else if err != nil {
		return "", fmt.Errorf("advance RuntimeRun command cursor: %w", err)
	}
	if _, err := repository.EnqueueOutboxMessage(ctx, outboxMessage); err != nil {
		return "", err
	}
	return safety.AppendInserted, nil
}

func runtimeCommandParams(
	tenantID tenancy.TenantID,
	command safety.RuntimeCommand,
	outboxMessage messaging.OutboundMessage,
) agentdb.InsertAgentRuntimeCommandParams {
	params := agentdb.InsertAgentRuntimeCommandParams{
		TenantID: string(tenantID), WorkOrderID: command.WorkOrderID,
		CommandID: command.CommandID, CommandDigest: command.CommandDigest,
		RuntimeRunID: command.RuntimeRunID, CommandSequence: command.CommandSequence,
		Type: string(command.Type), AuthorizedControlRequestID: optional(command.AuthorizedControlRequestID),
		SystemSafetyControlID:     optional(command.SystemSafetyControlID),
		SystemSafetyControlDigest: optional(command.SystemSafetyControlDigest),
		InputID:                   optional(command.InputID), InputContentDigest: optional(command.InputContentDigest),
		ApprovalComment: "", SpawnRequestID: optional(command.SpawnRequestID),
		ChildAdmissionDecisionID:     optional(command.ChildAdmissionDecisionID),
		ChildAdmissionDecisionDigest: optional(command.ChildAdmissionDecisionDigest),
		SpawnOutcome:                 optional(string(command.SpawnOutcome)), SpawnReasonCodes: command.SpawnReasonCodes,
		ChildAgentRunID: optional(command.ChildAgentRunID), Reason: optional(command.Reason),
		InvocationID: command.InvocationID, InvocationAttemptID: command.InvocationAttemptID,
		FencingToken: command.FencingToken, IdempotencyKey: command.IdempotencyKey,
		DeadlineAt: timestamp(command.DeadlineAt), CreatedAt: timestamp(command.CreatedAt),
		OutboxMessageID: outboxMessage.MessageID, OutboxPayloadDigest: outboxMessage.PayloadDigest,
		OutboxDestination: outboxMessage.Destination, OutboxAvailableAt: timestamp(outboxMessage.AvailableAt),
		OutboxCreatedAt: timestamp(outboxMessage.CreatedAt),
	}
	if command.Approval != nil {
		params.ApprovalID = optional(command.Approval.ApprovalID)
		params.ApprovalDecision = optional(command.Approval.Decision)
		params.ApprovalComment = command.Approval.Comment
	}
	return params
}

func validateRuntimeCommandOutbox(command safety.RuntimeCommand, message messaging.OutboundMessage) error {
	return validateControlOutbox(command.Payload, command.CreatedAt, command.DeadlineAt, message)
}

func validateSafetyControlOutbox(control safety.SystemSafetyControl, message messaging.OutboundMessage) error {
	return validateControlOutbox(control.Payload, control.IssuedAt, control.IssuedAt, message)
}

func validateControlOutbox(
	payload func() ([]byte, error),
	issuedAt time.Time,
	deadlineAt time.Time,
	message messaging.OutboundMessage,
) error {
	if err := message.Validate(); err != nil {
		return err
	}
	issuedAt = safety.DatabaseTime(issuedAt)
	if message.Destination != runtimeControlOutboxDestination ||
		!safety.DatabaseTime(message.CreatedAt).Equal(issuedAt) ||
		!safety.DatabaseTime(message.AvailableAt).Equal(issuedAt) ||
		safety.DatabaseTime(message.AvailableAt).After(safety.DatabaseTime(deadlineAt)) {
		return fmt.Errorf("%w: Outbox route or timestamps do not match control issuance", messaging.ErrOutboxConflict)
	}
	expected, err := payload()
	if err != nil {
		return err
	}
	if !bytes.Equal(expected, message.Payload) || messaging.PayloadDigest(expected) != message.PayloadDigest {
		return fmt.Errorf("%w: Outbox payload does not match control digest input", safety.ErrDigestConflict)
	}
	return nil
}

func (repository *RuntimeControlRepository) verifySystemSafetyAuthority(
	ctx context.Context,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
) error {
	if err := control.Validate(tenantID); err != nil {
		return err
	}
	if repository.safetyAuthorityVerifier == nil {
		return safety.ErrSafetyAuthorityUnverified
	}
	if err := repository.safetyAuthorityVerifier.VerifySystemSafetyAuthority(ctx, tenantID, control); err != nil {
		return fmt.Errorf("%w: %w", safety.ErrSafetyAuthorityUnverified, err)
	}
	return nil
}

func normalizeRuntimeControlAuthorities(
	authorities RuntimeControlAuthorities,
) (RuntimeControlAuthorities, error) {
	counts := []int{
		len(authorities.WorkOrders), len(authorities.AgentRuns), len(authorities.RuntimeRuns),
		len(authorities.Invocations), len(authorities.ControlRequests), len(authorities.ChildAdmissions),
	}
	total := 0
	for _, count := range counts {
		if count > MaxRuntimeControlAuthorityBatch-total {
			return RuntimeControlAuthorities{}, safety.ErrInvalidAuthority
		}
		total += count
	}

	authorities.WorkOrders = sortedAuthorityCopy(authorities.WorkOrders, func(left, right safety.WorkOrderAuthority) bool {
		return left.WorkOrderID < right.WorkOrderID
	})
	authorities.AgentRuns = sortedAuthorityCopy(authorities.AgentRuns, func(left, right safety.AgentRunAuthority) bool {
		if left.WorkOrderID != right.WorkOrderID {
			return left.WorkOrderID < right.WorkOrderID
		}
		return left.AgentRunID < right.AgentRunID
	})
	authorities.RuntimeRuns = sortedAuthorityCopy(authorities.RuntimeRuns, func(left, right safety.RuntimeRunAuthority) bool {
		if left.WorkOrderID != right.WorkOrderID {
			return left.WorkOrderID < right.WorkOrderID
		}
		if left.AgentRunID != right.AgentRunID {
			return left.AgentRunID < right.AgentRunID
		}
		return left.RuntimeRunID < right.RuntimeRunID
	})
	authorities.Invocations = sortedAuthorityCopy(authorities.Invocations, func(left, right safety.InvocationAuthority) bool {
		if left.InvocationID != right.InvocationID {
			return left.InvocationID < right.InvocationID
		}
		if left.AttemptNumber != right.AttemptNumber {
			return left.AttemptNumber < right.AttemptNumber
		}
		return left.InvocationAttemptID < right.InvocationAttemptID
	})
	authorities.ControlRequests = sortedAuthorityCopy(authorities.ControlRequests, func(left, right safety.ControlRequestAuthority) bool {
		return left.ControlRequestID < right.ControlRequestID
	})
	authorities.ChildAdmissions = sortedAuthorityCopy(authorities.ChildAdmissions, func(left, right safety.ChildAdmissionAuthority) bool {
		if left.WorkOrderID != right.WorkOrderID {
			return left.WorkOrderID < right.WorkOrderID
		}
		if left.ParentAgentRunID != right.ParentAgentRunID {
			return left.ParentAgentRunID < right.ParentAgentRunID
		}
		return left.DecisionID < right.DecisionID
	})
	return authorities, nil
}

func validateRuntimeControlAuthorities(
	tenantID tenancy.TenantID,
	authorities RuntimeControlAuthorities,
) error {
	for _, authority := range authorities.WorkOrders {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	for _, authority := range authorities.AgentRuns {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	for _, authority := range authorities.RuntimeRuns {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	for _, authority := range authorities.Invocations {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	for _, authority := range authorities.ControlRequests {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	for _, authority := range authorities.ChildAdmissions {
		if err := authority.Validate(tenantID); err != nil {
			return err
		}
	}
	return nil
}

func lockAuthorityWorkOrders(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authorities RuntimeControlAuthorities,
) error {
	workOrderIDs := make(map[string]struct{})
	for _, authority := range authorities.WorkOrders {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}
	for _, authority := range authorities.AgentRuns {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}
	for _, authority := range authorities.RuntimeRuns {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}
	for _, authority := range authorities.Invocations {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}
	for _, authority := range authorities.ControlRequests {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}
	for _, authority := range authorities.ChildAdmissions {
		workOrderIDs[authority.WorkOrderID] = struct{}{}
	}

	ordered := make([]string, 0, len(workOrderIDs))
	for workOrderID := range workOrderIDs {
		ordered = append(ordered, workOrderID)
	}
	sort.Strings(ordered)
	for _, workOrderID := range ordered {
		if _, err := repository.queries.LockWorkOrder(ctx, agentdb.LockWorkOrderParams{
			TenantID: string(tenantID), WorkOrderID: workOrderID,
		}); err != nil {
			return classifyAuthorityRead("lock authority WorkOrder", err)
		}
	}
	return nil
}

func sortedAuthorityCopy[T any](values []T, less func(T, T) bool) []T {
	result := slices.Clone(values)
	sort.SliceStable(result, func(left, right int) bool {
		return less(result[left], result[right])
	})
	return result
}

func classifyAuthorityRead(operation string, err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return safety.ErrInvalidAuthority
	}
	return fmt.Errorf("%s: %w", operation, err)
}

func classifyControlWrite(operation string, err error) error {
	var databaseError *pgconn.PgError
	if errors.As(err, &databaseError) {
		switch databaseError.Code {
		case "23503", "23514", "23502":
			return safety.ErrInvalidAuthority
		case "23505":
			return safety.ErrDigestConflict
		}
	}
	return fmt.Errorf("%s: %w", operation, err)
}

func isTerminalRuntimeState(state string) bool {
	return state == "succeeded" || state == "failed" || state == "cancelled"
}

func optional(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}

func equalOptional(value *string, expected string) bool {
	return value == nil && expected == "" || value != nil && *value == expected
}

func admitWorkOrder(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.WorkOrderAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	_, err := repository.queries.InsertWorkOrderAuthority(ctx, agentdb.InsertWorkOrderAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID, State: string(authority.State),
		ActiveWorkVersion: authority.ActiveWorkVersion, ChildAdmissionOpen: authority.ChildAdmissionOpen,
		CreatedAt: timestamp(authority.CreatedAt),
	})
	if err == nil {
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return classifyControlWrite("admit WorkOrder authority", err)
	}
	row, err := repository.queries.GetWorkOrderAuthority(ctx, agentdb.GetWorkOrderAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
	})
	if err != nil || row.State != string(authority.State) || row.ActiveWorkVersion != authority.ActiveWorkVersion ||
		row.ChildAdmissionOpen != authority.ChildAdmissionOpen || !row.CreatedAt.Time.Equal(safety.DatabaseTime(authority.CreatedAt)) {
		return safety.ErrAuthorityConflict
	}
	return nil
}

func admitAgentRun(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.AgentRunAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	_, err := repository.queries.InsertAgentRunAuthority(ctx, agentdb.InsertAgentRunAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
		AgentRunID: authority.AgentRunID, RunKind: authority.RunKind,
		RequiredForWorkOrderCompletion: authority.RequiredForWorkOrderCompletion,
		State:                          string(authority.State), CreatedAt: timestamp(authority.CreatedAt),
	})
	if err == nil {
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return classifyControlWrite("admit AgentRun authority", err)
	}
	row, err := repository.queries.GetAgentRunAuthority(ctx, agentdb.GetAgentRunAuthorityParams{
		TenantID: string(tenantID), AgentRunID: authority.AgentRunID,
	})
	if err != nil || row.WorkOrderID != authority.WorkOrderID || row.RunKind != authority.RunKind ||
		row.RequiredForWorkOrderCompletion != authority.RequiredForWorkOrderCompletion ||
		row.State != string(authority.State) || !row.CreatedAt.Time.Equal(safety.DatabaseTime(authority.CreatedAt)) {
		return safety.ErrAuthorityConflict
	}
	return nil
}

func admitRuntimeRun(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.RuntimeRunAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	_, err := repository.queries.InsertAgentRuntimeRunAuthority(ctx, agentdb.InsertAgentRuntimeRunAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
		AgentRunID: authority.AgentRunID, RuntimeRunID: authority.RuntimeRunID,
		State: string(authority.State), CreatedAt: timestamp(authority.CreatedAt),
	})
	if err == nil {
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return classifyControlWrite("admit AgentRuntimeRun authority", err)
	}
	row, err := repository.queries.GetAgentRuntimeRunAuthority(ctx, agentdb.GetAgentRuntimeRunAuthorityParams{
		TenantID: string(tenantID), RuntimeRunID: authority.RuntimeRunID,
	})
	if err != nil || row.WorkOrderID != authority.WorkOrderID || row.AgentRunID != authority.AgentRunID ||
		row.State != string(authority.State) || !row.CreatedAt.Time.Equal(safety.DatabaseTime(authority.CreatedAt)) {
		return safety.ErrAuthorityConflict
	}
	return nil
}

func admitInvocation(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.InvocationAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	_, invocationErr := repository.queries.InsertRuntimeInvocationAuthority(ctx, agentdb.InsertRuntimeInvocationAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
		RuntimeRunID: authority.RuntimeRunID, InvocationID: authority.InvocationID,
		RequestDigest: authority.RequestDigest, CreatedAt: timestamp(authority.InvocationCreatedAt),
	})
	if errors.Is(invocationErr, pgx.ErrNoRows) {
		row, err := repository.queries.GetRuntimeInvocationAuthority(ctx, agentdb.GetRuntimeInvocationAuthorityParams{
			TenantID: string(tenantID), InvocationID: authority.InvocationID,
		})
		if err != nil || row.WorkOrderID != authority.WorkOrderID || row.RuntimeRunID != authority.RuntimeRunID ||
			row.RequestDigest != authority.RequestDigest ||
			!row.CreatedAt.Time.Equal(safety.DatabaseTime(authority.InvocationCreatedAt)) {
			return safety.ErrAuthorityConflict
		}
	} else if invocationErr != nil {
		return classifyControlWrite("admit RuntimeInvocation authority", invocationErr)
	}
	invocation, err := repository.queries.LockRuntimeInvocationForAttempt(
		ctx,
		agentdb.LockRuntimeInvocationForAttemptParams{
			TenantID: string(tenantID), InvocationID: authority.InvocationID,
		},
	)
	if err != nil {
		return classifyAuthorityRead("lock RuntimeInvocation authority", err)
	}
	existingAttempt, err := repository.queries.GetRuntimeInvocationAttemptAuthority(
		ctx,
		agentdb.GetRuntimeInvocationAttemptAuthorityParams{
			TenantID: string(tenantID), InvocationAttemptID: authority.InvocationAttemptID,
		},
	)
	if err == nil {
		if existingAttempt.WorkOrderID != authority.WorkOrderID ||
			existingAttempt.RuntimeRunID != authority.RuntimeRunID ||
			existingAttempt.InvocationID != authority.InvocationID ||
			existingAttempt.AttemptNumber != authority.AttemptNumber ||
			existingAttempt.FencingToken != authority.FencingToken ||
			!existingAttempt.CreatedAt.Time.Equal(safety.DatabaseTime(authority.AttemptCreatedAt)) ||
			invocation.LastAttemptNumber < authority.AttemptNumber ||
			invocation.CurrentFencingToken < authority.FencingToken {
			return safety.ErrAuthorityConflict
		}
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return fmt.Errorf("read RuntimeInvocationAttempt identity: %w", err)
	}
	if authority.AttemptNumber != invocation.LastAttemptNumber+1 {
		return safety.ErrSequenceConflict
	}
	if authority.FencingToken <= invocation.CurrentFencingToken {
		return safety.ErrStaleFencing
	}

	_, attemptErr := repository.queries.InsertRuntimeInvocationAttemptAuthority(
		ctx,
		agentdb.InsertRuntimeInvocationAttemptAuthorityParams{
			TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
			RuntimeRunID: authority.RuntimeRunID, InvocationID: authority.InvocationID,
			InvocationAttemptID: authority.InvocationAttemptID, AttemptNumber: authority.AttemptNumber,
			FencingToken: authority.FencingToken, CreatedAt: timestamp(authority.AttemptCreatedAt),
		},
	)
	if attemptErr == nil {
		_, err := repository.queries.AdvanceRuntimeInvocationAttemptCursor(
			ctx,
			agentdb.AdvanceRuntimeInvocationAttemptCursorParams{
				AttemptNumber: authority.AttemptNumber, FencingToken: authority.FencingToken,
				UpdatedAt: timestamp(authority.AttemptCreatedAt), TenantID: string(tenantID),
				InvocationID: authority.InvocationID,
			},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrStaleFencing
		}
		if err != nil {
			return fmt.Errorf("advance RuntimeInvocation Attempt cursor: %w", err)
		}
		return nil
	}
	if !errors.Is(attemptErr, pgx.ErrNoRows) {
		return classifyControlWrite("admit RuntimeInvocationAttempt authority", attemptErr)
	}
	return safety.ErrAuthorityConflict
}

func admitControlRequest(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.ControlRequestAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	params := agentdb.InsertWorkOrderControlRequestAuthorityParams{
		TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
		ControlRequestID: authority.ControlRequestID, RequestDigest: authority.RequestDigest,
		Action: string(authority.Action), ExpectedActiveWorkVersion: authority.ExpectedActiveWorkVersion,
		ApprovalComment: "", AcceptedAt: timestamp(authority.AcceptedAt),
	}
	if authority.Input != nil {
		params.InputID = optional(authority.Input.InputID)
		params.InputContentDigest = optional(authority.Input.ContentDigest)
	}
	if authority.Approval != nil {
		params.ApprovalID = optional(authority.Approval.ApprovalID)
		params.ApprovalDecision = optional(authority.Approval.Decision)
		params.ApprovalComment = authority.Approval.Comment
	}
	_, insertErr := repository.queries.InsertWorkOrderControlRequestAuthority(ctx, params)
	if errors.Is(insertErr, pgx.ErrNoRows) {
		row, err := repository.queries.GetWorkOrderControlRequestAuthority(
			ctx,
			agentdb.GetWorkOrderControlRequestAuthorityParams{
				TenantID: string(tenantID), ControlRequestID: authority.ControlRequestID,
			},
		)
		if err != nil || row.WorkOrderID != authority.WorkOrderID || row.RequestDigest != authority.RequestDigest ||
			row.Action != string(authority.Action) || row.ExpectedActiveWorkVersion != authority.ExpectedActiveWorkVersion ||
			!equalOptional(row.InputID, optionalValue(params.InputID)) ||
			!equalOptional(row.InputContentDigest, optionalValue(params.InputContentDigest)) ||
			!equalOptional(row.ApprovalID, optionalValue(params.ApprovalID)) ||
			!equalOptional(row.ApprovalDecision, optionalValue(params.ApprovalDecision)) ||
			row.ApprovalComment != params.ApprovalComment ||
			!row.AcceptedAt.Time.Equal(safety.DatabaseTime(authority.AcceptedAt)) {
			return safety.ErrAuthorityConflict
		}
	} else if insertErr != nil {
		return classifyControlWrite("admit WorkOrderControlRequest authority", insertErr)
	}
	if authority.Input == nil {
		return nil
	}
	_, inputErr := repository.queries.InsertWorkOrderControlInputAuthority(
		ctx,
		agentdb.InsertWorkOrderControlInputAuthorityParams{
			TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
			ControlRequestID: authority.ControlRequestID, InputID: authority.Input.InputID,
			InputMessageID: authority.Input.InputMessageID, ContentDigest: authority.Input.ContentDigest,
			AcceptedAt: timestamp(authority.AcceptedAt),
		},
	)
	if inputErr == nil {
		return nil
	}
	if !errors.Is(inputErr, pgx.ErrNoRows) {
		return classifyControlWrite("admit WorkOrderControlInput authority", inputErr)
	}
	row, err := repository.queries.GetWorkOrderControlInputAuthority(
		ctx,
		agentdb.GetWorkOrderControlInputAuthorityParams{
			TenantID: string(tenantID), ControlRequestID: authority.ControlRequestID,
		},
	)
	if err != nil || row.WorkOrderID != authority.WorkOrderID || row.InputID != authority.Input.InputID ||
		row.InputMessageID != authority.Input.InputMessageID || row.ContentDigest != authority.Input.ContentDigest ||
		!row.AcceptedAt.Time.Equal(safety.DatabaseTime(authority.AcceptedAt)) {
		return safety.ErrAuthorityConflict
	}
	return nil
}

func optionalValue(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func admitChildAdmission(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	authority safety.ChildAdmissionAuthority,
) error {
	if err := authority.Validate(tenantID); err != nil {
		return err
	}
	_, err := repository.queries.InsertChildAdmissionDecisionAuthority(
		ctx,
		agentdb.InsertChildAdmissionDecisionAuthorityParams{
			TenantID: string(tenantID), WorkOrderID: authority.WorkOrderID,
			DecisionID: authority.DecisionID, DecisionDigest: authority.DecisionDigest,
			SpawnRequestID: authority.SpawnRequestID, SpawnRequestDigest: authority.SpawnRequestDigest,
			ParentAgentRunID: authority.ParentAgentRunID, Outcome: string(authority.Outcome),
			ReasonCodes: authority.ReasonCodes, ChildAgentRunID: optional(authority.ChildAgentRunID),
			RuntimeRunID: optional(authority.RuntimeRunID), DecidedAt: timestamp(authority.DecidedAt),
		},
	)
	if err == nil {
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return classifyControlWrite("admit ChildAgentRunAdmissionDecision authority", err)
	}
	row, err := repository.queries.GetChildAdmissionDecisionAuthority(
		ctx,
		agentdb.GetChildAdmissionDecisionAuthorityParams{
			TenantID: string(tenantID), DecisionID: authority.DecisionID,
		},
	)
	if err != nil || row.WorkOrderID != authority.WorkOrderID || row.DecisionDigest != authority.DecisionDigest ||
		row.SpawnRequestID != authority.SpawnRequestID || row.SpawnRequestDigest != authority.SpawnRequestDigest ||
		row.ParentAgentRunID != authority.ParentAgentRunID || row.Outcome != string(authority.Outcome) ||
		!slices.Equal(row.ReasonCodes, authority.ReasonCodes) ||
		!equalOptional(row.ChildAgentRunID, authority.ChildAgentRunID) ||
		!equalOptional(row.RuntimeRunID, authority.RuntimeRunID) ||
		!row.DecidedAt.Time.Equal(safety.DatabaseTime(authority.DecidedAt)) {
		return safety.ErrAuthorityConflict
	}
	return nil
}
