package httpadapter

import (
	"bufio"
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/runtimeport"
	"github.com/shell-echo/agent/internal/runtimeport/contractprojection"
)

type installedInvocationFixture struct {
	Operation           string `json:"operation"`
	TokenPath           string `json:"token_path"`
	BodyPath            string `json:"body_path"`
	RuntimeRunID        string `json:"runtime_run_id"`
	InvocationID        string `json:"invocation_id"`
	InvocationAttemptID string `json:"invocation_attempt_id"`
	FencingToken        uint64 `json:"fencing_token"`
	RequestDigest       string `json:"request_digest"`
	AfterEventSequence  uint64 `json:"after_event_sequence"`
	Limit               uint32 `json:"limit"`
}

type installedFixture struct {
	InstalledModulePath string `json:"installed_module_path"`
	ConfigPath          string `json:"config_path"`
	StateRoot           string `json:"state_root"`
	ProviderRevisionID  string `json:"provider_revision_id"`
	Registry            struct {
		ResourceSHA256 string `json:"resource_sha256"`
		RegistryDigest string `json:"registry_digest"`
	} `json:"registry"`
	TLS struct {
		Algorithm             string `json:"algorithm"`
		CACertificatePath     string `json:"ca_certificate_path"`
		ClientCertificatePath string `json:"client_certificate_path"`
		ClientPrivateKeyPath  string `json:"client_private_key_path"`
		CAFingerprint         string `json:"ca_sha256_fingerprint"`
		ClientURISAN          string `json:"client_uri_san"`
		ClientTokenSubject    string `json:"client_token_subject"`
	} `json:"tls"`
	Start         installedInvocationFixture `json:"start"`
	Status        installedInvocationFixture `json:"status"`
	Command       installedInvocationFixture `json:"command"`
	Events        installedInvocationFixture `json:"events"`
	MissingStatus installedInvocationFixture `json:"missing_status"`
	StaleCommand  installedInvocationFixture `json:"stale_command"`
}

type installedProviderProcess struct {
	command *exec.Cmd
	stderr  *bytes.Buffer
	done    chan error
	stop    sync.Once
}

func TestInstalledCrossLanguageFiveOperations(t *testing.T) {
	fixture, adapter, provider := installedTestComposition(t)
	defer provider.Stop(t)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	capabilitiesRequest, err := runtimeport.NewCapabilitiesRequest(fixture.ProviderRevisionID)
	if err != nil {
		t.Fatal(err)
	}
	capabilities, ok := adapter.Capabilities(ctx, capabilitiesRequest).Value()
	if !ok || capabilities.ProviderRevisionID() != fixture.ProviderRevisionID {
		t.Fatalf("Capabilities result differs: %v", capabilities)
	}

	startRequest := installedMutationRequest(t, runtimeport.OperationStart, fixture.Start)
	startOutcome := adapter.Start(ctx, startRequest.(runtimeport.StartRequest))
	assertInstalledAccepted(t, startOutcome, runtimeport.OperationStart, fixture.Start.RuntimeRunID, 1)

	statusRequest, err := runtimeport.NewStatusRequest(installedInvocation(t, runtimeport.OperationReadStatus, fixture.Status))
	if err != nil {
		t.Fatal(err)
	}
	status, ok := adapter.Status(ctx, statusRequest).Value()
	if !ok || status.RuntimeRunID() != fixture.Start.RuntimeRunID || status.ObservedFencingToken() != 1 {
		t.Fatalf("Status result differs: %v", status)
	}

	commandRequest := installedMutationRequest(t, runtimeport.OperationCommand, fixture.Command)
	commandOutcome := adapter.Command(ctx, commandRequest.(runtimeport.CommandRequest))
	assertInstalledAccepted(t, commandOutcome, runtimeport.OperationCommand, fixture.Start.RuntimeRunID, 2)

	eventsRequest, err := runtimeport.NewEventsRequest(
		installedInvocation(t, runtimeport.OperationReadEvents, fixture.Events),
		fixture.Events.AfterEventSequence,
		fixture.Events.Limit,
	)
	if err != nil {
		t.Fatal(err)
	}
	events, ok := adapter.Events(ctx, eventsRequest).Value()
	if !ok || events.RuntimeRunID() != fixture.Start.RuntimeRunID || events.NextEventSequence() < 1 {
		t.Fatalf("Events result differs: %v", events)
	}
	if _, err := os.Stat(filepath.Join(fixture.StateRoot, "runtime.sqlite3")); err != nil {
		t.Fatalf("real Provider-local SQLite is absent: %v", err)
	}

	t.Log("installed-cross-language-evidence:installed-wheel-process-ed25519-mtls-http11-sqlite:passed")
	t.Log("installed-cross-language-evidence:five-operation-happy-path:passed")
}

func TestInstalledCrossLanguageClosedFailures(t *testing.T) {
	fixture, adapter, provider := installedTestComposition(t)
	defer provider.Stop(t)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	startRequest := installedMutationRequest(t, runtimeport.OperationStart, fixture.Start)
	assertInstalledAccepted(t, adapter.Start(ctx, startRequest.(runtimeport.StartRequest)), runtimeport.OperationStart, fixture.Start.RuntimeRunID, 1)
	commandRequest := installedMutationRequest(t, runtimeport.OperationCommand, fixture.Command)
	assertInstalledAccepted(t, adapter.Command(ctx, commandRequest.(runtimeport.CommandRequest)), runtimeport.OperationCommand, fixture.Start.RuntimeRunID, 2)

	badSignature := fixture.Status
	token := readInstalledSecret(t, badSignature.TokenPath)
	if strings.HasSuffix(token, "A") {
		token = token[:len(token)-1] + "B"
	} else {
		token = token[:len(token)-1] + "A"
	}
	badSignature.TokenPath = writeInstalledSecret(t, filepath.Dir(badSignature.TokenPath), "bad-signature.token", []byte(token))
	badStatus, err := runtimeport.NewStatusRequest(installedInvocation(t, runtimeport.OperationReadStatus, badSignature))
	if err != nil {
		t.Fatal(err)
	}
	if class := failureClass(t, adapter.Status(ctx, badStatus)); class != runtimeport.FailureAuthenticationRejected {
		t.Fatalf("bad signature class = %s", class)
	}

	missingStatus, err := runtimeport.NewStatusRequest(installedInvocation(t, runtimeport.OperationReadStatus, fixture.MissingStatus))
	if err != nil {
		t.Fatal(err)
	}
	if class := failureClass(t, adapter.Status(ctx, missingStatus)); class != runtimeport.FailureNotFound {
		t.Fatalf("missing status class = %s", class)
	}

	staleRequest := installedMutationRequest(t, runtimeport.OperationCommand, fixture.StaleCommand)
	staleOutcome := adapter.Command(ctx, staleRequest.(runtimeport.CommandRequest))
	if staleOutcome.Validate() != nil || staleOutcome.Disposition() != runtimeport.MutationRejected {
		t.Fatalf("stale Command outcome = %v", staleOutcome)
	}
	failure, ok := staleOutcome.Failure()
	if !ok || failure.Class() != runtimeport.FailureProtocolConflict {
		t.Fatalf("stale Command failure = %v", failure)
	}

	t.Log("installed-cross-language-evidence:closed-known-failures:passed")
}

func installedTestComposition(t *testing.T) (installedFixture, *Adapter, *installedProviderProcess) {
	t.Helper()
	installedBin := os.Getenv("AGENT_NATIVE_RUNTIME_INSTALLED_BIN")
	installedPython := os.Getenv("AGENT_NATIVE_RUNTIME_INSTALLED_PYTHON")
	fixtureScript := os.Getenv("AGENT_CROSS_LANGUAGE_FIXTURE")
	if installedBin == "" || installedPython == "" || fixtureScript == "" {
		t.Skip("installed Native Runtime cross-language environment is not configured")
	}
	root := filepath.Join(t.TempDir(), "fixture")
	manifestPath := filepath.Join(filepath.Dir(root), "fixture-manifest.json")
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	command := exec.CommandContext(ctx, installedPython, fixtureScript, "--output-root", root, "--manifest", manifestPath)
	command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	var stderr bytes.Buffer
	command.Stdout = io.Discard
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		t.Fatalf("prepare installed fixture: %v; stderr=%s", err, stderr.String())
	}
	var fixture installedFixture
	readInstalledJSON(t, manifestPath, &fixture)
	if fixture.TLS.Algorithm != "Ed25519" || !strings.HasPrefix(fixture.TLS.CAFingerprint, "sha256:") ||
		fixture.Registry.ResourceSHA256 == fixture.Registry.RegistryDigest ||
		strings.Contains(fixture.InstalledModulePath, "/runtime/native/src/") {
		t.Fatal("installed fixture identity or source binding differs")
	}

	migrate := exec.CommandContext(ctx, filepath.Join(installedBin, "agent-native-runtime-migrate"), "--config", fixture.ConfigPath)
	migrate.Stdout = io.Discard
	migrate.Stderr = &stderr
	if err := migrate.Run(); err != nil {
		t.Fatalf("installed migrate: %v; stderr=%s", err, stderr.String())
	}
	provider, port := startInstalledProvider(t, ctx, filepath.Join(installedBin, "agent-native-runtime-serve"), fixture.ConfigPath)
	client := installedTLSClient(t, fixture)
	configuration := testConfiguration()
	configuration.Endpoint = fmt.Sprintf("https://127.0.0.1:%d", port)
	configuration.ProviderRevisionID = fixture.ProviderRevisionID
	configuration.Client = client
	configuration.Validator = installedContractValidator(t, fixture.Registry.RegistryDigest)
	configuration.Limits.CapabilitiesTimeout = 5 * time.Second
	configuration.Limits.ReadTimeout = 5 * time.Second
	configuration.Limits.MutationTimeout = 5 * time.Second
	adapter, err := New(configuration)
	if err != nil {
		provider.Stop(t)
		t.Fatal(err)
	}
	return fixture, adapter, provider
}

func startInstalledProvider(t *testing.T, ctx context.Context, executable, configPath string) (*installedProviderProcess, int) {
	t.Helper()
	command := exec.CommandContext(ctx, executable, "--config", configPath)
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	stderr := &bytes.Buffer{}
	command.Stderr = stderr
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	provider := &installedProviderProcess{command: command, stderr: stderr, done: make(chan error, 1)}
	go func() { provider.done <- command.Wait() }()
	ready := make(chan struct {
		port int
		err  error
	}, 1)
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			var event struct {
				Event string `json:"event"`
				Port  int    `json:"port"`
			}
			if json.Unmarshal(scanner.Bytes(), &event) == nil && event.Event == "listener_ready" && event.Port > 0 {
				ready <- struct {
					port int
					err  error
				}{port: event.Port}
				return
			}
		}
		ready <- struct {
			port int
			err  error
		}{err: scanner.Err()}
	}()
	select {
	case result := <-ready:
		if result.err != nil || result.port < 1 {
			provider.Stop(t)
			t.Fatalf("installed serve readiness failed: %v; stderr=%s", result.err, stderr.String())
		}
		return provider, result.port
	case err := <-provider.done:
		t.Fatalf("installed serve exited before readiness: %v; stderr=%s", err, stderr.String())
	case <-time.After(10 * time.Second):
		provider.Stop(t)
		t.Fatalf("installed serve readiness timed out; stderr=%s", stderr.String())
	}
	return nil, 0
}

func (provider *installedProviderProcess) Stop(t *testing.T) {
	t.Helper()
	provider.stop.Do(func() {
		if provider.command.Process == nil {
			return
		}
		_ = provider.command.Process.Signal(syscall.SIGTERM)
		select {
		case err := <-provider.done:
			if err != nil {
				t.Errorf("installed serve stop: %v; stderr=%s", err, provider.stderr.String())
			}
		case <-time.After(5 * time.Second):
			_ = provider.command.Process.Kill()
			<-provider.done
			t.Errorf("installed serve drain timed out")
		}
	})
}

func installedTLSClient(t *testing.T, fixture installedFixture) *http.Client {
	t.Helper()
	caPEM, err := os.ReadFile(fixture.TLS.CACertificatePath)
	if err != nil {
		t.Fatal(err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		t.Fatal("installed CA certificate is invalid")
	}
	certificate, err := tls.LoadX509KeyPair(fixture.TLS.ClientCertificatePath, fixture.TLS.ClientPrivateKeyPath)
	if err != nil {
		t.Fatal(err)
	}
	return &http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{
		MinVersion:   tls.VersionTLS12,
		RootCAs:      pool,
		Certificates: []tls.Certificate{certificate},
	}}}
}

func installedContractValidator(t *testing.T, registryDigest string) *contractprojection.RuntimeDocumentValidator {
	t.Helper()
	digest, err := runtimeport.NewDigest(registryDigest)
	if err != nil {
		t.Fatal(err)
	}
	validator, err := contractprojection.NewRuntimeDocumentValidator(
		adapterSchemaDocuments(t),
		contractprojection.DocumentLimits{MaxBytes: 8 * 1024 * 1024, MaxDepth: 64, MaxNodes: 100_000, MaxNumberTokenBytes: 1024},
		contractprojection.RuntimeEventRegistryBinding{ID: "agent-runtime-core", Version: 1, Digest: digest},
	)
	if err != nil {
		t.Fatal(err)
	}
	return validator
}

func installedMutationRequest(t *testing.T, operation runtimeport.Operation, fixture installedInvocationFixture) any {
	t.Helper()
	documentBytes, err := os.ReadFile(fixture.BodyPath)
	if err != nil {
		t.Fatal(err)
	}
	document, err := runtimeport.NewContractDocument(documentBytes, 8*1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	invocation := installedInvocation(t, operation, fixture)
	if operation == runtimeport.OperationStart {
		request, requestErr := runtimeport.NewStartRequest(invocation, document)
		if requestErr != nil {
			t.Fatal(requestErr)
		}
		return request
	}
	request, err := runtimeport.NewCommandRequest(invocation, document)
	if err != nil {
		t.Fatal(err)
	}
	return request
}

func installedInvocation(t *testing.T, operation runtimeport.Operation, fixture installedInvocationFixture) runtimeport.Invocation {
	t.Helper()
	tokenBytes, err := os.ReadFile(fixture.TokenPath)
	if err != nil {
		t.Fatal(err)
	}
	token, err := runtimeport.NewInvocationToken(tokenBytes, 16*1024)
	if err != nil {
		t.Fatal(err)
	}
	digest, err := runtimeport.NewDigest(fixture.RequestDigest)
	if err != nil {
		t.Fatal(err)
	}
	invocation, err := runtimeport.NewInvocation(
		operation,
		testProviderRevisionID,
		fixture.RuntimeRunID,
		fixture.InvocationID,
		fixture.InvocationAttemptID,
		fixture.FencingToken,
		digest,
		token,
	)
	if err != nil {
		t.Fatal(err)
	}
	return invocation
}

func assertInstalledAccepted(t *testing.T, outcome runtimeport.MutationOutcome, operation runtimeport.Operation, runtimeRunID string, fencingToken uint64) {
	t.Helper()
	if outcome.Validate() != nil || outcome.Disposition() != runtimeport.MutationAccepted || outcome.Reference().Operation() != operation {
		t.Fatalf("mutation outcome = %v", outcome)
	}
	status, ok := outcome.AcceptedStatus()
	if !ok || status.RuntimeRunID() != runtimeRunID || status.ObservedFencingToken() != fencingToken {
		t.Fatalf("accepted status = %v", status)
	}
}

func readInstalledJSON(t *testing.T, path string, target any) {
	t.Helper()
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(encoded, target); err != nil {
		t.Fatal(err)
	}
}

func readInstalledSecret(t *testing.T, path string) string {
	t.Helper()
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	value := string(encoded)
	if strings.Count(value, ".") != 2 || len(value) < 64 {
		t.Fatal(errors.New("installed fixture token is invalid"))
	}
	return value
}

func writeInstalledSecret(t *testing.T, root, name string, value []byte) string {
	t.Helper()
	path := filepath.Join(root, name)
	if err := os.WriteFile(path, value, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
