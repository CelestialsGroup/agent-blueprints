package httpadapter

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/runtimeport"
	"github.com/shell-echo/agent/internal/runtimeport/contractprojection"
)

const (
	testProviderRevisionID = "apr_01J00000000000000000000000"
	testRuntimeRunID       = "rtr_01J00000000000000000000000"
	testRegistryDigest     = "sha256:eaae5ff3a467b85bbb5bb1cdbba4dd4b5546d7f5fb1cb1c17e37565bec55ae8c"
	testBearerToken        = "header.payload.signature"
)

func TestReadOperationsUseExactAuthenticatedHTTP11Routes(t *testing.T) {
	capabilities := adapterContractExample(t, "agent-runtime-capabilities.json")
	status := adapterContractExample(t, "agent-runtime-run-status.json")
	events := adapterContractExample(t, "agent-runtime-event-page.json")
	var requests atomic.Int64
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		if request.Method != http.MethodGet || request.ProtoMajor != 1 || request.ProtoMinor != 1 ||
			request.TLS == nil || len(request.TLS.PeerCertificates) != 1 {
			t.Errorf("unexpected authenticated request shape")
		}
		switch request.URL.RequestURI() {
		case "/v1/capabilities":
			if len(request.Header.Values("Authorization")) != 0 {
				t.Error("Capabilities carried bearer authority")
			}
			writeAdapterJSON(writer, http.StatusOK, capabilities)
		case "/v1/runs/" + testRuntimeRunID:
			assertSingleBearer(t, request)
			writeAdapterJSON(writer, http.StatusOK, status)
		case "/v1/runs/" + testRuntimeRunID + "/events?after_event_sequence=41&limit=1":
			assertSingleBearer(t, request)
			writeAdapterJSON(writer, http.StatusOK, events)
		default:
			t.Errorf("unexpected request target %q", request.URL.RequestURI())
			writeAdapterJSON(writer, http.StatusNotFound, standardErrorDocument())
		}
	}))

	capabilitiesRequest, err := runtimeport.NewCapabilitiesRequest(testProviderRevisionID)
	if err != nil {
		t.Fatal(err)
	}
	capabilitiesResult := adapter.Capabilities(context.Background(), capabilitiesRequest)
	capabilitiesValue, ok := capabilitiesResult.Value()
	if !ok || capabilitiesValue.ProviderRevisionID() != testProviderRevisionID {
		t.Fatalf("Capabilities result = %v", capabilitiesResult)
	}

	statusInvocation := testReadInvocation(t, runtimeport.OperationReadStatus, 2, testBearerToken)
	statusRequest, err := runtimeport.NewStatusRequest(statusInvocation)
	if err != nil {
		t.Fatal(err)
	}
	statusResult := adapter.Status(context.Background(), statusRequest)
	statusValue, ok := statusResult.Value()
	if !ok || statusValue.RuntimeRunID() != testRuntimeRunID || statusValue.ObservedFencingToken() != 2 {
		t.Fatalf("Status result = %v", statusResult)
	}

	eventsInvocation := testReadInvocation(t, runtimeport.OperationReadEvents, 2, testBearerToken)
	eventsRequest, err := runtimeport.NewEventsRequest(eventsInvocation, 41, 1)
	if err != nil {
		t.Fatal(err)
	}
	eventsResult := adapter.Events(context.Background(), eventsRequest)
	eventsValue, ok := eventsResult.Value()
	if !ok || eventsValue.RuntimeRunID() != testRuntimeRunID || eventsValue.NextEventSequence() != 42 {
		t.Fatalf("Events result = %v", eventsResult)
	}
	if requests.Load() != 3 {
		t.Fatalf("request count = %d", requests.Load())
	}
	t.Log("http-adapter-evidence:real-mtls-http11-read-routes:passed")
}

func TestCapabilitiesBindsCanonicalImmutabilityUnderConcurrency(t *testing.T) {
	capabilities := adapterContractExample(t, "agent-runtime-capabilities.json")
	driftedBody := mutateAdapterDocument(t, capabilities, func(document map[string]any) {
		document["runtime_version"] = "2026.08"
	})
	var returnDrift atomic.Bool
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		if returnDrift.Load() {
			writeAdapterJSON(writer, http.StatusOK, driftedBody)
			return
		}
		writeAdapterJSON(writer, http.StatusOK, capabilities)
	}))
	request, err := runtimeport.NewCapabilitiesRequest(testProviderRevisionID)
	if err != nil {
		t.Fatal(err)
	}
	var wait sync.WaitGroup
	errorsSeen := make(chan string, 24)
	for range 24 {
		wait.Add(1)
		go func() {
			defer wait.Done()
			if result := adapter.Capabilities(context.Background(), request); !result.Succeeded() {
				errorsSeen <- result.String()
			}
		}()
	}
	wait.Wait()
	close(errorsSeen)
	for result := range errorsSeen {
		t.Fatalf("concurrent result = %s", result)
	}

	returnDrift.Store(true)
	if result := adapter.Capabilities(context.Background(), request); failureClass(t, result) != runtimeport.FailureInvalidResponse {
		t.Fatal("changed canonical Capabilities was not rejected")
	}
	t.Log("http-adapter-evidence:capabilities-canonical-concurrency:passed")
}

func TestReadStatusMapsOnlyDeclaredFailures(t *testing.T) {
	for _, item := range []struct {
		status int
		class  runtimeport.FailureClass
	}{
		{http.StatusUnauthorized, runtimeport.FailureAuthenticationRejected},
		{http.StatusForbidden, runtimeport.FailureAuthorityRejected},
		{http.StatusNotFound, runtimeport.FailureNotFound},
		{http.StatusInternalServerError, runtimeport.FailureInternal},
		{http.StatusServiceUnavailable, runtimeport.FailureUnavailable},
		{http.StatusBadRequest, runtimeport.FailureInvalidResponse},
		{http.StatusTooManyRequests, runtimeport.FailureInvalidResponse},
	} {
		t.Run(strconv.Itoa(item.status), func(t *testing.T) {
			adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writeAdapterJSON(writer, item.status, standardErrorDocument())
			}))
			request, err := runtimeport.NewStatusRequest(testReadInvocation(t, runtimeport.OperationReadStatus, 2, testBearerToken))
			if err != nil {
				t.Fatal(err)
			}
			result := adapter.Status(context.Background(), request)
			failure, ok := result.Failure()
			if !ok || failure.Class() != item.class {
				t.Fatalf("failure = %v", failure)
			}
			if item.class != runtimeport.FailureInvalidResponse {
				if failure.Code() != "RUNTIME_TEST_ERROR" {
					t.Fatalf("code = %q", failure.Code())
				}
				if details, exists := failure.Details(); !exists || string(details.Bytes()) != `{"reason":"bounded"}` {
					t.Fatalf("details = %q, %v", details.Bytes(), exists)
				}
			}
			if strings.Contains(failure.String(), "sensitive provider message") {
				t.Fatal("StandardError message leaked")
			}
		})
	}
	t.Log("http-adapter-evidence:closed-read-status-authority-map:passed")
}

func TestReadAdapterRejectsResponseAndIdentityDrift(t *testing.T) {
	capabilities := adapterContractExample(t, "agent-runtime-capabilities.json")
	handlers := map[string]http.HandlerFunc{
		"content type": func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Type", "application/json; charset=utf-8")
			writer.Header().Set("Content-Length", strconv.Itoa(len(capabilities)))
			writer.WriteHeader(http.StatusOK)
			_, _ = writer.Write(capabilities)
		},
		"chunked": func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusOK)
			writer.(http.Flusher).Flush()
			_, _ = writer.Write(capabilities)
		},
		"content encoding": func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Encoding", "gzip")
			writeAdapterJSON(writer, http.StatusOK, capabilities)
		},
		"noncanonical length": func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Type", "application/json")
			writer.Header().Set("Content-Length", "0"+strconv.Itoa(len(capabilities)))
			writer.WriteHeader(http.StatusOK)
			_, _ = writer.Write(capabilities)
		},
		"truncated": func(writer http.ResponseWriter, _ *http.Request) {
			connection, buffer, err := writer.(http.Hijacker).Hijack()
			if err != nil {
				t.Error(err)
				return
			}
			defer connection.Close()
			_, _ = buffer.WriteString("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + strconv.Itoa(len(capabilities)+5) + "\r\nConnection: close\r\n\r\n")
			_, _ = buffer.Write(capabilities)
			_ = buffer.Flush()
		},
	}
	request, err := runtimeport.NewCapabilitiesRequest(testProviderRevisionID)
	if err != nil {
		t.Fatal(err)
	}
	for name, handler := range handlers {
		t.Run(name, func(t *testing.T) {
			adapter := testTLSAdapter(t, 1024*1024, handler)
			if class := failureClass(t, adapter.Capabilities(context.Background(), request)); class != runtimeport.FailureInvalidResponse {
				t.Fatalf("class = %s", class)
			}
		})
	}

	t.Run("oversized", func(t *testing.T) {
		adapter := testTLSAdapter(t, 256, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writeAdapterJSON(writer, http.StatusOK, capabilities)
		}))
		if class := failureClass(t, adapter.Capabilities(context.Background(), request)); class != runtimeport.FailureInvalidResponse {
			t.Fatalf("class = %s", class)
		}
	})

	t.Run("status identity", func(t *testing.T) {
		status := mutateAdapterDocument(t, adapterContractExample(t, "agent-runtime-run-status.json"), func(document map[string]any) {
			document["runtime_run_id"] = "different-runtime-run"
		})
		adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writeAdapterJSON(writer, http.StatusOK, status)
		}))
		statusRequest, err := runtimeport.NewStatusRequest(testReadInvocation(t, runtimeport.OperationReadStatus, 2, testBearerToken))
		if err != nil {
			t.Fatal(err)
		}
		if class := failureClass(t, adapter.Status(context.Background(), statusRequest)); class != runtimeport.FailureInvalidResponse {
			t.Fatalf("class = %s", class)
		}
	})

	t.Run("status fencing", func(t *testing.T) {
		status := mutateAdapterDocument(t, adapterContractExample(t, "agent-runtime-run-status.json"), func(document map[string]any) {
			document["observed_fencing_token"] = float64(3)
		})
		adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writeAdapterJSON(writer, http.StatusOK, status)
		}))
		statusRequest, err := runtimeport.NewStatusRequest(testReadInvocation(t, runtimeport.OperationReadStatus, 2, testBearerToken))
		if err != nil {
			t.Fatal(err)
		}
		if class := failureClass(t, adapter.Status(context.Background(), statusRequest)); class != runtimeport.FailureInvalidResponse {
			t.Fatalf("class = %s", class)
		}
	})

	t.Run("capabilities provider revision", func(t *testing.T) {
		body := mutateAdapterDocument(t, capabilities, func(document map[string]any) {
			document["provider_revision_id"] = "different-provider-revision"
		})
		adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writeAdapterJSON(writer, http.StatusOK, body)
		}))
		if class := failureClass(t, adapter.Capabilities(context.Background(), request)); class != runtimeport.FailureInvalidResponse {
			t.Fatalf("class = %s", class)
		}
	})

	t.Run("event cursor", func(t *testing.T) {
		events := mutateAdapterDocument(t, adapterContractExample(t, "agent-runtime-event-page.json"), func(document map[string]any) {
			document["next_event_sequence"] = float64(43)
		})
		adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writeAdapterJSON(writer, http.StatusOK, events)
		}))
		eventsRequest, err := runtimeport.NewEventsRequest(testReadInvocation(t, runtimeport.OperationReadEvents, 2, testBearerToken), 41, 1)
		if err != nil {
			t.Fatal(err)
		}
		if class := failureClass(t, adapter.Events(context.Background(), eventsRequest)); class != runtimeport.FailureInvalidResponse {
			t.Fatalf("class = %s", class)
		}
	})

	for name, mutate := range map[string]func(map[string]any){
		"event run identity": func(document map[string]any) {
			events := document["events"].([]any)
			events[0].(map[string]any)["runtime_run_id"] = "different-runtime-run"
		},
		"event ordering": func(document map[string]any) {
			events := document["events"].([]any)
			second := make(map[string]any, len(events[0].(map[string]any)))
			for key, value := range events[0].(map[string]any) {
				second[key] = value
			}
			second["event_id"] = "second-event"
			second["event_sequence"] = float64(41)
			document["events"] = append(events, second)
			document["next_event_sequence"] = float64(41)
		},
		"event limit": func(document map[string]any) {
			events := document["events"].([]any)
			second := make(map[string]any, len(events[0].(map[string]any)))
			for key, value := range events[0].(map[string]any) {
				second[key] = value
			}
			second["event_id"] = "second-event"
			second["event_sequence"] = float64(43)
			document["events"] = append(events, second)
			document["next_event_sequence"] = float64(43)
		},
	} {
		t.Run(name, func(t *testing.T) {
			events := mutateAdapterDocument(t, adapterContractExample(t, "agent-runtime-event-page.json"), mutate)
			adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writeAdapterJSON(writer, http.StatusOK, events)
			}))
			limit := uint32(2)
			if name == "event limit" {
				limit = 1
			}
			eventsRequest, err := runtimeport.NewEventsRequest(testReadInvocation(t, runtimeport.OperationReadEvents, 2, testBearerToken), 41, limit)
			if err != nil {
				t.Fatal(err)
			}
			if class := failureClass(t, adapter.Events(context.Background(), eventsRequest)); class != runtimeport.FailureInvalidResponse {
				t.Fatalf("class = %s", class)
			}
		})
	}
	t.Log("http-adapter-evidence:strict-response-identity-cursor-bounds:passed")
}

func TestEventReadMapsDeclaredCursorExpiry(t *testing.T) {
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writeAdapterJSON(writer, http.StatusGone, standardErrorDocument())
	}))
	request, err := runtimeport.NewEventsRequest(testReadInvocation(t, runtimeport.OperationReadEvents, 2, testBearerToken), 41, 1)
	if err != nil {
		t.Fatal(err)
	}
	if class := failureClass(t, adapter.Events(context.Background(), request)); class != runtimeport.FailureCursorExpired {
		t.Fatalf("class = %s", class)
	}
}

func TestReadAdapterDoesNotDispatchInvalidAuthorityOrFollowRedirect(t *testing.T) {
	var requests atomic.Int64
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		if request.URL.Path == "/redirected" {
			t.Error("redirect was followed")
		}
		writer.Header().Set("Location", "/redirected")
		writeAdapterJSON(writer, http.StatusFound, standardErrorDocument())
	}))
	badTokenRequest, err := runtimeport.NewStatusRequest(testReadInvocation(t, runtimeport.OperationReadStatus, 2, "not-compact"))
	if err != nil {
		t.Fatal(err)
	}
	if class := failureClass(t, adapter.Status(context.Background(), badTokenRequest)); class != runtimeport.FailureInvalidRequest {
		t.Fatalf("class = %s", class)
	}
	if requests.Load() != 0 {
		t.Fatalf("invalid token request count = %d", requests.Load())
	}
	capabilitiesRequest, err := runtimeport.NewCapabilitiesRequest(testProviderRevisionID)
	if err != nil {
		t.Fatal(err)
	}
	if class := failureClass(t, adapter.Capabilities(context.Background(), capabilitiesRequest)); class != runtimeport.FailureInvalidResponse {
		t.Fatalf("class = %s", class)
	}
	if requests.Load() != 1 {
		t.Fatalf("redirect request count = %d", requests.Load())
	}
}

func testTLSAdapter(t *testing.T, maxResponseBytes int64, handler http.Handler) *Adapter {
	t.Helper()
	server := testTLSServer(t, handler)
	configuration := testTLSConfiguration(t, server)
	configuration.Limits.MaxResponseBytes = maxResponseBytes
	configuration.ProviderRevisionID = testProviderRevisionID
	configuration.Validator = adapterContractValidator(t)
	adapter, err := New(configuration)
	if err != nil {
		t.Fatal(err)
	}
	return adapter
}

type adapterTestServer struct {
	server            *httptest.Server
	clientCertificate tls.Certificate
	rootCAs           *x509.CertPool
}

func testTLSServer(t *testing.T, handler http.Handler) adapterTestServer {
	t.Helper()
	ca, caKey := testCertificateAuthority(t)
	serverCertificate := testLeafCertificate(t, ca, caKey, false)
	clientCertificate := testLeafCertificate(t, ca, caKey, true)
	pool := x509.NewCertPool()
	pool.AddCert(ca)
	server := httptest.NewUnstartedServer(handler)
	server.EnableHTTP2 = false
	server.TLS = &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{serverCertificate},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    pool,
		NextProtos:   []string{"http/1.1"},
	}
	server.StartTLS()
	t.Cleanup(server.Close)
	return adapterTestServer{server: server, clientCertificate: clientCertificate, rootCAs: pool}
}

func testTLSConfiguration(t *testing.T, bundle adapterTestServer) Configuration {
	t.Helper()
	configuration := testConfiguration()
	configuration.Endpoint = bundle.server.URL
	configuration.Client = &http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{
		MinVersion:   tls.VersionTLS12,
		RootCAs:      bundle.rootCAs,
		Certificates: []tls.Certificate{bundle.clientCertificate},
	}}}
	return configuration
}

func testCertificateAuthority(t *testing.T) (*x509.Certificate, ed25519.PrivateKey) {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "runtime-adapter-test-ca"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, publicKey, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return certificate, privateKey
}

func testLeafCertificate(t *testing.T, ca *x509.Certificate, caKey ed25519.PrivateKey, client bool) tls.Certificate {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	serial := int64(2)
	extendedUsage := []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(serial),
		Subject:      pkix.Name{CommonName: "runtime-provider"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  extendedUsage,
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1"), net.ParseIP("::1")},
		DNSNames:     []string{"localhost"},
	}
	if client {
		template.SerialNumber = big.NewInt(3)
		template.Subject = pkix.Name{CommonName: "agent-platform-test-client"}
		template.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
		template.IPAddresses = nil
		template.DNSNames = nil
	}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, publicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: privateKey}
}

func adapterContractValidator(t *testing.T) *contractprojection.RuntimeDocumentValidator {
	t.Helper()
	digest, err := runtimeport.NewDigest(testRegistryDigest)
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

type adapterProjectionManifest struct {
	Schemas []struct {
		Path string `json:"path"`
		ID   string `json:"id"`
	} `json:"schemas"`
}

func adapterSchemaDocuments(t *testing.T) []contractprojection.SchemaDocument {
	t.Helper()
	var manifest adapterProjectionManifest
	readAdapterJSON(t, filepath.Join(adapterApplicationRoot(t), "internal", "generated", "runtimeapi", "projection-manifest.json"), &manifest)
	documents := make([]contractprojection.SchemaDocument, 0, len(manifest.Schemas))
	for _, item := range manifest.Schemas {
		var document any
		readAdapterJSON(t, filepath.Join(adapterContractRoot(t), filepath.FromSlash(item.Path)), &document)
		documents = append(documents, contractprojection.SchemaDocument{ID: item.ID, Document: document})
	}
	return documents
}

func adapterApplicationRoot(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func adapterContractRoot(t *testing.T) string {
	t.Helper()
	if configured := os.Getenv("AGENT_CONTRACT_ROOT"); configured != "" {
		return configured
	}
	root, err := filepath.Abs(filepath.Join("..", "..", "..", "..", "contract"))
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func adapterContractExample(t *testing.T, name string) []byte {
	t.Helper()
	encoded, err := os.ReadFile(filepath.Join(adapterContractRoot(t), "examples", "contracts", name))
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func readAdapterJSON(t *testing.T, path string, target any) {
	t.Helper()
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(encoded, target); err != nil {
		t.Fatal(err)
	}
}

func writeAdapterJSON(writer http.ResponseWriter, status int, encoded []byte) {
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("Content-Length", strconv.Itoa(len(encoded)))
	writer.WriteHeader(status)
	_, _ = writer.Write(encoded)
}

func standardErrorDocument() []byte {
	return []byte(`{"code":"RUNTIME_TEST_ERROR","message":"sensitive provider message","retryable":true,"trace_id":"trace-test","details":{"reason":"bounded"}}`)
}

func mutateAdapterDocument(t *testing.T, encoded []byte, mutate func(map[string]any)) []byte {
	t.Helper()
	var document map[string]any
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	mutate(document)
	result, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func testReadInvocation(t *testing.T, operation runtimeport.Operation, fencingToken uint64, tokenValue string) runtimeport.Invocation {
	t.Helper()
	digest, err := runtimeport.NewDigest("sha256:" + strings.Repeat("a", 64))
	if err != nil {
		t.Fatal(err)
	}
	token, err := runtimeport.NewInvocationToken([]byte(tokenValue), 16*1024)
	if err != nil {
		t.Fatal(err)
	}
	invocation, err := runtimeport.NewInvocation(
		operation,
		testProviderRevisionID,
		testRuntimeRunID,
		"invocation-test",
		"attempt-test",
		fencingToken,
		digest,
		token,
	)
	if err != nil {
		t.Fatal(err)
	}
	return invocation
}

func assertSingleBearer(t *testing.T, request *http.Request) {
	t.Helper()
	values := request.Header.Values("Authorization")
	if len(values) != 1 || values[0] != "Bearer "+testBearerToken {
		t.Errorf("authorization = %v", values)
	}
}

func failureClass[T any](t *testing.T, result runtimeport.ReadResult[T]) runtimeport.FailureClass {
	t.Helper()
	failure, ok := result.Failure()
	if !ok {
		t.Fatalf("expected failure, result = %v", result)
	}
	return failure.Class()
}
