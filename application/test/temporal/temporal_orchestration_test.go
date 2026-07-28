//go:build temporalintegration

package temporal_test

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5/pgxpool"
	enumspb "go.temporal.io/api/enums/v1"
	historypb "go.temporal.io/api/history/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"google.golang.org/protobuf/encoding/protojson"

	domain "github.com/shell-echo/agent/internal/domain/orchestration"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/orchestration/temporaladapter"
	"github.com/shell-echo/agent/internal/persistence"
	"github.com/shell-echo/agent/internal/safety"
)

const integrationTimeout = 90 * time.Second

func TestTemporalStartRecoveryContinueAsNewAndReplayHistory(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), integrationTimeout)
	defer cancel()

	applicationPool := openPool(t, requiredEnv(t, "AGENT_TEST_APPLICATION_DSN"))
	runner, err := persistence.NewTransactionRunner(applicationPool)
	if err != nil {
		t.Fatalf("create transaction runner: %v", err)
	}
	workflowRuns, err := persistence.NewWorkflowRunRepository(runner)
	if err != nil {
		t.Fatalf("create WorkflowRun repository: %v", err)
	}
	runtimeControl, err := persistence.NewRuntimeControlRepository(runner)
	if err != nil {
		t.Fatalf("create WorkOrder authority repository: %v", err)
	}
	clientApplications, err := persistence.NewClientApplicationRepository(runner)
	if err != nil {
		t.Fatalf("create ClientApplication repository: %v", err)
	}

	config := temporaladapter.DefaultConfig()
	config.Address = requiredEnv(t, "AGENT_TEST_TEMPORAL_ADDRESS")
	config.Namespace = requiredEnv(t, "AGENT_TEST_TEMPORAL_NAMESPACE")
	config.TaskQueue = requiredEnv(t, "AGENT_TEST_TEMPORAL_TASK_QUEUE")
	config.EngineVersion = requiredEnv(t, "AGENT_TEST_TEMPORAL_ENGINE_VERSION")
	config.WorkerDeployment = requiredEnv(t, "AGENT_TEST_WORKER_DEPLOYMENT")
	config.WorkerBuildID = requiredEnv(t, "AGENT_TEST_WORKER_BUILD_ID")

	temporalClient, err := client.DialContext(ctx, client.Options{
		HostPort: config.Address, Namespace: config.Namespace,
		Identity: "agent-b03.1-integration-client",
	})
	if err != nil {
		t.Fatalf("dial Temporal: %v", err)
	}
	t.Cleanup(temporalClient.Close)

	flaky := &retryOnceConfirmer{repository: workflowRuns}
	activities, err := temporaladapter.NewActivities(flaky)
	if err != nil {
		t.Fatalf("create Activities: %v", err)
	}
	temporalWorker := startWorker(t, temporalClient, config, activities)
	promoteWorkerBuild(t, ctx, temporalClient, config)

	suffix := fmt.Sprintf("%d", time.Now().UTC().UnixNano())
	bootstrapTenant(t, ctx, clientApplications, suffix)
	first := admitStartRequest(t, ctx, runtimeControl, "recovery-"+suffix)
	lostClient := &lostStartResponseClient{Client: temporalClient}
	starter, err := temporaladapter.NewStarter(lostClient, config)
	if err != nil {
		t.Fatalf("create lost-response starter: %v", err)
	}
	receipt, err := starter.Start(ctx, first)
	if err != nil {
		t.Fatalf("reconcile lost start response: %v", err)
	}
	if receipt.Outcome != domain.StartReconciled {
		t.Fatalf("lost response outcome = %s, want reconciled", receipt.Outcome)
	}
	persisted := waitForWorkflowRun(t, ctx, workflowRuns, first.TenantID, first.WorkflowRunID)
	if persisted.OrchestrationBinding.NativeExecutionReferenceDigest != receipt.NativeExecutionReferenceDigest {
		t.Fatal("start receipt and Activity confirmation native digests differ")
	}
	if flaky.attempts.Load() < 2 {
		t.Fatalf("confirmation Activity attempts = %d, want retry", flaky.attempts.Load())
	}

	regularStarter, err := temporaladapter.NewStarter(temporalClient, config)
	if err != nil {
		t.Fatalf("create starter: %v", err)
	}
	replayed, err := regularStarter.Start(ctx, first)
	if err != nil || replayed.Outcome != domain.StartReconciled {
		t.Fatalf("duplicate start receipt=%#v error=%v", replayed, err)
	}
	conflicting := first
	conflicting.Workflow.DefinitionDigest = "sha256:" + strings.Repeat("f", 64)
	if _, err := regularStarter.Start(ctx, conflicting); !errors.Is(err, temporaladapter.ErrStartConflict) {
		t.Fatalf("conflicting start error = %v, want ErrStartConflict", err)
	}
	if _, err := workflowRuns.Get(ctx, "tenant-b", first.WorkflowRunID); !errors.Is(err, domain.ErrWorkflowRunNotFound) {
		t.Fatalf("cross-Tenant WorkflowRun read = %v, want not found", err)
	}

	temporalWorker.Stop()
	temporalWorker = startWorker(t, temporalClient, config, activities)
	if err := temporalClient.SignalWorkflow(
		ctx, "work-order/"+first.WorkOrderID, "", temporaladapter.ControlSignal,
		temporaladapter.ControlComplete,
	); err != nil {
		t.Fatalf("signal recovered Workflow: %v", err)
	}
	if err := temporalClient.GetWorkflow(ctx, "work-order/"+first.WorkOrderID, "").Get(ctx, nil); err != nil {
		t.Fatalf("wait for recovered Workflow: %v", err)
	}
	history := readHistory(t, ctx, temporalClient, "work-order/"+first.WorkOrderID)
	assertHistoryHygiene(t, history)
	writeHistoryEvidence(t, history)

	second := admitStartRequest(t, ctx, runtimeControl, "continue-"+suffix)
	if _, err := regularStarter.Start(ctx, second); err != nil {
		t.Fatalf("start Continue-as-New Workflow: %v", err)
	}
	beforeContinue := waitForWorkflowRun(t, ctx, workflowRuns, second.TenantID, second.WorkflowRunID)
	before := describeRunID(t, ctx, temporalClient, second.WorkOrderID)
	if err := temporalClient.SignalWorkflow(
		ctx, "work-order/"+second.WorkOrderID, "", temporaladapter.ControlSignal,
		temporaladapter.ControlContinueAsNew,
	); err != nil {
		t.Fatalf("signal Continue-as-New: %v", err)
	}
	waitForNewRunID(t, ctx, temporalClient, second.WorkOrderID, before)
	afterContinue := waitForWorkflowRun(t, ctx, workflowRuns, second.TenantID, second.WorkflowRunID)
	if !beforeContinue.Matches(afterContinue) {
		t.Fatal("Continue-as-New changed the immutable Platform WorkflowRun")
	}
	if err := temporalClient.SignalWorkflow(
		ctx, "work-order/"+second.WorkOrderID, "", temporaladapter.ControlSignal,
		temporaladapter.ControlComplete,
	); err != nil {
		t.Fatalf("complete continued Workflow: %v", err)
	}
	if err := temporalClient.GetWorkflow(ctx, "work-order/"+second.WorkOrderID, "").Get(ctx, nil); err != nil {
		t.Fatalf("wait for continued Workflow: %v", err)
	}
	temporalWorker.Stop()
}

func bootstrapTenant(
	t *testing.T,
	ctx context.Context,
	repository *persistence.ClientApplicationRepository,
	suffix string,
) {
	t.Helper()
	const tenantID = tenancy.TenantID("tenant-a")
	createdAt := time.Date(2026, time.July, 28, 0, 0, 0, 0, time.UTC)
	_, err := repository.Register(
		ctx,
		tenancy.Tenant{ID: tenantID, DisplayName: "Temporal Integration Tenant", CreatedAt: createdAt},
		tenancy.ClientApplication{
			TenantID: tenantID, ID: tenancy.ClientApplicationID("client-" + suffix),
			DisplayName: "Temporal Integration Client", CreatedAt: createdAt,
		},
	)
	if err != nil {
		t.Fatalf("bootstrap Tenant: %v", err)
	}
}

func startWorker(
	t *testing.T,
	temporalClient client.Client,
	config temporaladapter.Config,
	activities *temporaladapter.Activities,
) worker.Worker {
	t.Helper()
	result, err := temporaladapter.NewWorker(temporalClient, config, activities)
	if err != nil {
		t.Fatalf("create Temporal worker: %v", err)
	}
	if err := result.Start(); err != nil {
		t.Fatalf("start Temporal worker: %v", err)
	}
	t.Cleanup(result.Stop)
	return result
}

func promoteWorkerBuild(
	t *testing.T,
	ctx context.Context,
	temporalClient client.Client,
	config temporaladapter.Config,
) {
	t.Helper()
	handle := temporalClient.WorkerDeploymentClient().GetHandle(config.WorkerDeployment)
	var lastErr error
	for ctx.Err() == nil {
		_, lastErr = handle.SetCurrentVersion(ctx, client.WorkerDeploymentSetCurrentVersionOptions{
			BuildID: config.WorkerBuildID,
		})
		if lastErr == nil {
			return
		}
		select {
		case <-ctx.Done():
		case <-time.After(250 * time.Millisecond):
		}
	}
	t.Fatalf("promote Worker Build ID: %v", lastErr)
}

func admitStartRequest(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	suffix string,
) domain.StartRequest {
	t.Helper()
	createdAt := time.Now().UTC().Truncate(time.Microsecond)
	tenantID := tenancy.TenantID("tenant-a")
	workOrderID := "work-order-" + suffix
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{{
			TenantID: tenantID, WorkOrderID: workOrderID,
			State: safety.WorkOrderAccepted, ActiveWorkVersion: 1,
			ChildAdmissionOpen: true, CreatedAt: createdAt,
		}},
	}); err != nil {
		t.Fatalf("admit WorkOrder: %v", err)
	}
	return domain.StartRequest{
		TenantID: tenantID, WorkOrderID: workOrderID,
		WorkflowRunID:       "workflow-run-" + suffix,
		WorkflowExecutionID: "workflow-execution-" + suffix,
		Workflow: domain.WorkflowDefinition{
			ID: "workflow.agent-execution", Version: "1.0.0",
			DefinitionBuildID: requiredEnv(t, "AGENT_TEST_WORKER_BUILD_ID"),
			DefinitionDigest:  requiredEnv(t, "AGENT_TEST_WORKFLOW_DEFINITION_DIGEST"),
		},
		CreatedAt: createdAt,
	}
}

func waitForWorkflowRun(
	t *testing.T,
	ctx context.Context,
	repository *persistence.WorkflowRunRepository,
	tenantID tenancy.TenantID,
	workflowRunID string,
) domain.WorkflowRun {
	t.Helper()
	for ctx.Err() == nil {
		run, err := repository.Get(ctx, tenantID, workflowRunID)
		if err == nil {
			return run
		}
		if !errors.Is(err, domain.ErrWorkflowRunNotFound) {
			t.Fatalf("read WorkflowRun: %v", err)
		}
		select {
		case <-ctx.Done():
		case <-time.After(100 * time.Millisecond):
		}
	}
	t.Fatalf("wait for WorkflowRun: %v", ctx.Err())
	return domain.WorkflowRun{}
}

func describeRunID(t *testing.T, ctx context.Context, temporalClient client.Client, workOrderID string) string {
	t.Helper()
	description, err := temporalClient.DescribeWorkflowExecution(ctx, "work-order/"+workOrderID, "")
	if err != nil {
		t.Fatalf("describe Workflow: %v", err)
	}
	return description.GetWorkflowExecutionInfo().GetExecution().GetRunId()
}

func waitForNewRunID(
	t *testing.T,
	ctx context.Context,
	temporalClient client.Client,
	workOrderID string,
	previous string,
) {
	t.Helper()
	for ctx.Err() == nil {
		if current := describeRunID(t, ctx, temporalClient, workOrderID); current != previous {
			return
		}
		select {
		case <-ctx.Done():
		case <-time.After(100 * time.Millisecond):
		}
	}
	t.Fatalf("Continue-as-New did not create a new native Run: %v", ctx.Err())
}

func readHistory(
	t *testing.T,
	ctx context.Context,
	temporalClient client.Client,
	workflowID string,
) *historypb.History {
	t.Helper()
	iterator := temporalClient.GetWorkflowHistory(
		ctx, workflowID, "", false, enumspb.HISTORY_EVENT_FILTER_TYPE_ALL_EVENT,
	)
	history := &historypb.History{}
	for iterator.HasNext() {
		event, err := iterator.Next()
		if err != nil {
			t.Fatalf("read Workflow History: %v", err)
		}
		history.Events = append(history.Events, event)
	}
	if len(history.Events) == 0 {
		t.Fatal("Workflow History is empty")
	}
	return history
}

func assertHistoryHygiene(t *testing.T, history *historypb.History) {
	t.Helper()
	encoded, err := protojson.Marshal(history)
	if err != nil {
		t.Fatalf("encode Workflow History: %v", err)
	}
	for _, forbidden := range []string{
		requiredEnv(t, "AGENT_TEST_APPLICATION_DSN"),
		requiredEnv(t, "AGENT_TEST_TEMPORAL_ADDRESS"),
		"authorization", "bearer ", "prompt", "secret", "password",
	} {
		if strings.Contains(strings.ToLower(string(encoded)), strings.ToLower(forbidden)) {
			t.Fatalf("Workflow History contains forbidden value %q", forbidden)
		}
	}
	var value any
	if err := json.Unmarshal(encoded, &value); err != nil {
		t.Fatalf("decode Workflow History JSON for payload scan: %v", err)
	}
	scanHistoryPayloadData(t, value)
}

func scanHistoryPayloadData(t *testing.T, value any) {
	t.Helper()
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if key == "data" {
				encoded, ok := child.(string)
				if !ok {
					t.Fatal("Workflow History payload data is not encoded text")
				}
				payload, err := base64.StdEncoding.DecodeString(encoded)
				if err != nil {
					t.Fatalf("decode Workflow History payload data: %v", err)
				}
				assertHistoryPayloadHygiene(t, payload)
				continue
			}
			scanHistoryPayloadData(t, child)
		}
	case []any:
		for _, child := range typed {
			scanHistoryPayloadData(t, child)
		}
	}
}

func assertHistoryPayloadHygiene(t *testing.T, payload []byte) {
	t.Helper()
	if len(payload) > 16*1024 || !utf8.Valid(payload) {
		t.Fatal("Workflow History payload is not bounded UTF-8 text")
	}
	lower := strings.ToLower(string(payload))
	for _, forbidden := range []string{
		"authorization", "bearer ", "credential", "endpoint", "password",
		"prompt", "secret", "token", "http://", "https://", "postgres://",
	} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("Workflow History decoded payload contains forbidden term %q", forbidden)
		}
	}
}

func writeHistoryEvidence(t *testing.T, history *historypb.History) {
	t.Helper()
	path := os.Getenv("AGENT_TEST_HISTORY_OUTPUT")
	if path == "" {
		return
	}
	encoded, err := protojson.MarshalOptions{Indent: "  "}.Marshal(history)
	if err != nil {
		t.Fatalf("encode History evidence: %v", err)
	}
	encoded = append(encoded, '\n')
	if err := os.WriteFile(path, encoded, 0o600); err != nil {
		t.Fatalf("write History evidence: %v", err)
	}
}

func requiredEnv(t *testing.T, name string) string {
	t.Helper()
	value := os.Getenv(name)
	if value == "" {
		t.Fatalf("%s is required", name)
	}
	return value
}

type retryOnceConfirmer struct {
	repository *persistence.WorkflowRunRepository
	attempts   atomic.Int32
}

func (confirmer *retryOnceConfirmer) ConfirmWorkflowStart(
	ctx context.Context,
	tenantID tenancy.TenantID,
	run domain.WorkflowRun,
) (domain.ConfirmOutcome, error) {
	if confirmer.attempts.Add(1) == 1 {
		return "", errors.New("injected transient PostgreSQL boundary failure")
	}
	return confirmer.repository.ConfirmWorkflowStart(ctx, tenantID, run)
}

type lostStartResponseClient struct {
	client.Client
}

func (lost *lostStartResponseClient) ExecuteWorkflow(
	ctx context.Context,
	options client.StartWorkflowOptions,
	workflow interface{},
	args ...interface{},
) (client.WorkflowRun, error) {
	run, err := lost.Client.ExecuteWorkflow(ctx, options, workflow, args...)
	if err != nil {
		return run, err
	}
	return run, context.DeadlineExceeded
}

func openPool(t *testing.T, dsn string) *pgxpool.Pool {
	t.Helper()
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatalf("parse PostgreSQL DSN: %v", err)
	}
	config.MaxConns = 4
	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		t.Fatalf("open PostgreSQL pool: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}
