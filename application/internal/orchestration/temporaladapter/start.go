package temporaladapter

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"

	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/api/serviceerror"
	workflowservice "go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/converter"

	domain "github.com/shell-echo/agent/internal/domain/orchestration"
)

var (
	ErrStartConflict       = errors.New("orchestration start identity conflict")
	ErrStartFailed         = errors.New("orchestration start rejected before acceptance")
	ErrStartOutcomeUnknown = errors.New("orchestration start outcome is unknown")
)

type startClient interface {
	ExecuteWorkflow(
		context.Context,
		client.StartWorkflowOptions,
		interface{},
		...interface{},
	) (client.WorkflowRun, error)
	DescribeWorkflowExecution(
		context.Context,
		string,
		string,
	) (*workflowservice.DescribeWorkflowExecutionResponse, error)
}

// Starter starts and reconciles stable WorkOrder Workflow identities.
type Starter struct {
	client startClient
	config Config
}

// NewStarter creates a Temporal start adapter. It performs no network I/O.
func NewStarter(temporalClient startClient, config Config) (*Starter, error) {
	if temporalClient == nil {
		return nil, errors.New("temporal client is required")
	}
	if err := config.Validate(); err != nil {
		return nil, err
	}
	return &Starter{client: temporalClient, config: config}, nil
}

// Start creates the stable execution or reconciles a compatible prior start.
// It never opens a PostgreSQL transaction and never treats a timeout as failure.
func (starter *Starter) Start(
	ctx context.Context,
	request domain.StartRequest,
) (domain.StartReceipt, error) {
	if err := request.Validate(); err != nil {
		return domain.StartReceipt{}, err
	}
	temporalWorkflowID, err := workflowID(request.WorkOrderID)
	if err != nil {
		return domain.StartReceipt{}, err
	}
	startDigest, err := startIdentityDigest(request, starter.config, temporalWorkflowID)
	if err != nil {
		return domain.StartReceipt{}, err
	}
	input := WorkflowInput{
		TenantID: string(request.TenantID), WorkOrderID: request.WorkOrderID,
		WorkflowRunID: request.WorkflowRunID, WorkflowExecutionID: request.WorkflowExecutionID,
		WorkflowID: request.Workflow.ID, WorkflowVersion: request.Workflow.Version,
		DefinitionBuildID:   request.Workflow.DefinitionBuildID,
		DefinitionDigest:    request.Workflow.DefinitionDigest,
		EngineVersion:       starter.config.EngineVersion,
		WorkerDeployment:    starter.config.WorkerDeployment,
		WorkerBuildID:       starter.config.WorkerBuildID,
		StartIdentityDigest: startDigest, CreatedAt: request.CreatedAt,
		ActivitySchedule: starter.config.ActivitySchedule,
		ActivityStart:    starter.config.ActivityStart,
	}
	run, executeErr := starter.client.ExecuteWorkflow(
		ctx,
		client.StartWorkflowOptions{
			ID: temporalWorkflowID, TaskQueue: starter.config.TaskQueue,
			WorkflowExecutionTimeout:                 starter.config.WorkflowExecution,
			WorkflowRunTimeout:                       starter.config.WorkflowRun,
			WorkflowTaskTimeout:                      starter.config.WorkflowTask,
			WorkflowIDConflictPolicy:                 enumspb.WORKFLOW_ID_CONFLICT_POLICY_FAIL,
			WorkflowIDReusePolicy:                    enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
			WorkflowExecutionErrorWhenAlreadyStarted: true,
			Memo:                                     map[string]interface{}{StartIdentityMemoKey: startDigest},
		},
		WorkflowType,
		input,
	)
	if executeErr == nil && run != nil && run.GetID() == temporalWorkflowID && run.GetRunID() != "" {
		return receiptForNativeExecution(
			request, starter.config.Namespace, run.GetID(), run.GetRunID(), domain.StartCreated,
		)
	}
	if executeErr == nil {
		executeErr = errors.New("temporal returned an incomplete or mismatched execution handle")
	}

	receipt, reconcileErr := starter.reconcile(ctx, request, temporalWorkflowID, startDigest)
	if reconcileErr == nil {
		return receipt, nil
	}
	if errors.Is(reconcileErr, ErrStartConflict) {
		return domain.StartReceipt{}, reconcileErr
	}
	var alreadyStarted *serviceerror.WorkflowExecutionAlreadyStarted
	if errors.As(executeErr, &alreadyStarted) || isUncertainStartError(executeErr) {
		return domain.StartReceipt{}, fmt.Errorf(
			"%w: execute: %v; reconcile: %v", ErrStartOutcomeUnknown, executeErr, reconcileErr,
		)
	}
	return domain.StartReceipt{}, fmt.Errorf("%w: %v", ErrStartFailed, executeErr)
}

func (starter *Starter) reconcile(
	ctx context.Context,
	request domain.StartRequest,
	temporalWorkflowID string,
	expectedDigest string,
) (domain.StartReceipt, error) {
	description, err := starter.client.DescribeWorkflowExecution(ctx, temporalWorkflowID, "")
	if err != nil {
		return domain.StartReceipt{}, fmt.Errorf("describe stable Workflow execution: %w", err)
	}
	info := description.GetWorkflowExecutionInfo()
	if info == nil || info.GetExecution() == nil || info.GetType() == nil {
		return domain.StartReceipt{}, fmt.Errorf("%w: incomplete execution description", ErrStartConflict)
	}
	if info.GetType().GetName() != WorkflowType || info.GetExecution().GetWorkflowId() != temporalWorkflowID {
		return domain.StartReceipt{}, fmt.Errorf("%w: incompatible workflow type or ID", ErrStartConflict)
	}
	payload := info.GetMemo().GetFields()[StartIdentityMemoKey]
	if payload == nil {
		return domain.StartReceipt{}, fmt.Errorf("%w: start identity memo is absent", ErrStartConflict)
	}
	var actualDigest string
	if err := converter.GetDefaultDataConverter().FromPayload(payload, &actualDigest); err != nil {
		return domain.StartReceipt{}, fmt.Errorf("%w: decode start identity memo: %v", ErrStartConflict, err)
	}
	if actualDigest != expectedDigest {
		return domain.StartReceipt{}, fmt.Errorf("%w: start identity digest differs", ErrStartConflict)
	}
	return receiptForNativeExecution(
		request,
		starter.config.Namespace,
		info.GetExecution().GetWorkflowId(),
		info.GetExecution().GetRunId(),
		domain.StartReconciled,
	)
}

func startIdentityDigest(
	request domain.StartRequest,
	config Config,
	temporalWorkflowID string,
) (string, error) {
	values := map[string]string{
		"created_at":            request.CreatedAt.Format("2006-01-02T15:04:05.999999Z07:00"),
		"definition_build_id":   request.Workflow.DefinitionBuildID,
		"definition_digest":     request.Workflow.DefinitionDigest,
		"engine_id":             EngineID,
		"engine_version":        config.EngineVersion,
		"task_queue":            config.TaskQueue,
		"tenant_id":             string(request.TenantID),
		"temporal_workflow_id":  temporalWorkflowID,
		"versioning_behavior":   VersioningBehavior,
		"worker_build_id":       config.WorkerBuildID,
		"worker_deployment":     config.WorkerDeployment,
		"work_order_id":         request.WorkOrderID,
		"workflow_execution_id": request.WorkflowExecutionID,
		"workflow_id":           request.Workflow.ID,
		"workflow_run_id":       request.WorkflowRunID,
		"workflow_version":      request.Workflow.Version,
	}
	payload, err := json.Marshal(values)
	if err != nil {
		return "", fmt.Errorf("encode start identity: %w", err)
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func receiptForNativeExecution(
	request domain.StartRequest,
	namespace string,
	temporalWorkflowID string,
	runID string,
	outcome domain.StartOutcome,
) (domain.StartReceipt, error) {
	digest, err := digestNativeExecution(namespace, temporalWorkflowID, runID)
	if err != nil {
		return domain.StartReceipt{}, err
	}
	return domain.StartReceipt{
		WorkflowRunID:                  request.WorkflowRunID,
		WorkOrderID:                    request.WorkOrderID,
		NativeExecutionReferenceDigest: digest,
		Outcome:                        outcome,
	}, nil
}

func isUncertainStartError(err error) bool {
	var invalidArgument *serviceerror.InvalidArgument
	var namespaceNotFound *serviceerror.NamespaceNotFound
	var permissionDenied *serviceerror.PermissionDenied
	var failedPrecondition *serviceerror.FailedPrecondition
	return !(errors.As(err, &invalidArgument) || errors.As(err, &namespaceNotFound) ||
		errors.As(err, &permissionDenied) || errors.As(err, &failedPrecondition))
}
