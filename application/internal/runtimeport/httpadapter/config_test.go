package httpadapter

import (
	"crypto/tls"
	"crypto/x509"
	"errors"
	"net/http"
	"net/http/cookiejar"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/runtimeport"
)

type rejectingValidator struct{}

func (rejectingValidator) ValidateMutationRequest(runtimeport.Operation, runtimeport.Invocation, []byte) error {
	return errors.New("not exercised")
}

func (rejectingValidator) ValidateSuccessResponse(runtimeport.Operation, []byte) error {
	return errors.New("not exercised")
}

func (rejectingValidator) ValidateErrorResponse([]byte) error {
	return errors.New("not exercised")
}

func TestNewRejectsMissingHarnessAuthorityAndUnsafeDefaults(t *testing.T) {
	valid := testConfiguration()
	for name, change := range map[string]func(*Configuration){
		"http endpoint":         func(configuration *Configuration) { configuration.Endpoint = "http://127.0.0.1:8443" },
		"endpoint path":         func(configuration *Configuration) { configuration.Endpoint = "https://127.0.0.1:8443/v1" },
		"missing endpoint host": func(configuration *Configuration) { configuration.Endpoint = "https://:8443" },
		"missing client":        func(configuration *Configuration) { configuration.Client = nil },
		"missing validator":     func(configuration *Configuration) { configuration.Validator = nil },
		"default transport":     func(configuration *Configuration) { configuration.Client = &http.Client{} },
		"environment proxy": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).Proxy = http.ProxyFromEnvironment
		},
		"custom dial": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).DialContext = http.DefaultTransport.(*http.Transport).DialContext
		},
		"cookie jar": func(configuration *Configuration) {
			configuration.Client.Jar, _ = cookiejar.New(nil)
		},
		"default trust": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).TLSClientConfig.RootCAs = nil
		},
		"missing client identity": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).TLSClientConfig.Certificates = nil
		},
		"empty client identity": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).TLSClientConfig.Certificates = []tls.Certificate{{Certificate: [][]byte{{1}}}}
		},
		"unsafe TLS": func(configuration *Configuration) {
			configuration.Client.Transport.(*http.Transport).TLSClientConfig.MinVersion = tls.VersionTLS11
		},
		"hidden timeout":     func(configuration *Configuration) { configuration.Client.Timeout = time.Second },
		"unbounded response": func(configuration *Configuration) { configuration.Limits.MaxResponseBytes = 0 },
		"unbounded start request": func(configuration *Configuration) {
			configuration.Limits.MaxStartRequestBytes = 0
		},
		"unbounded command request": func(configuration *Configuration) {
			configuration.Limits.MaxCommandRequestBytes = 0
		},
	} {
		t.Run(name, func(t *testing.T) {
			configuration := valid
			transport := valid.Client.Transport.(*http.Transport).Clone()
			transport.TLSClientConfig = valid.Client.Transport.(*http.Transport).TLSClientConfig.Clone()
			client := *valid.Client
			client.Transport = transport
			configuration.Client = &client
			change(&configuration)
			if _, err := New(configuration); !errors.Is(err, ErrInvalidConfiguration) {
				t.Fatalf("error = %v", err)
			}
		})
	}
}

func TestNewClonesAndBoundsInjectedClient(t *testing.T) {
	configuration := testConfiguration()
	adapter, err := New(configuration)
	if err != nil {
		t.Fatal(err)
	}
	if adapter.endpoint.String() != "https://127.0.0.1:8443" || adapter.providerRevisionID != configuration.ProviderRevisionID {
		t.Fatal("immutable endpoint binding differs")
	}
	cloned := adapter.client.Transport.(*http.Transport)
	original := configuration.Client.Transport.(*http.Transport)
	if cloned == original || cloned.TLSClientConfig == original.TLSClientConfig {
		t.Fatal("injected client or TLS configuration was not cloned")
	}
	if !cloned.DisableCompression || !cloned.DisableKeepAlives || cloned.ForceAttemptHTTP2 ||
		cloned.MaxConnsPerHost != configuration.Limits.MaxConnections ||
		cloned.MaxResponseHeaderBytes != configuration.Limits.MaxResponseHeaderBytes {
		t.Fatal("bounded transport configuration differs")
	}
	if adapter.client.CheckRedirect == nil {
		t.Fatal("redirect policy is absent")
	}
}

func testConfiguration() Configuration {
	pool := x509.NewCertPool()
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{
			MinVersion:   tls.VersionTLS12,
			RootCAs:      pool,
			Certificates: []tls.Certificate{{Certificate: [][]byte{{1}}, PrivateKey: struct{}{}}},
		},
	}
	return Configuration{
		Endpoint:           "https://127.0.0.1:8443",
		ProviderRevisionID: "provider-revision-1",
		Client:             &http.Client{Transport: transport},
		Validator:          rejectingValidator{},
		Limits: Limits{
			MaxConnections:         4,
			MaxResponseHeaderBytes: 16 * 1024,
			MaxResponseBytes:       1024 * 1024,
			MaxTokenBytes:          16 * 1024,
			MaxStartRequestBytes:   8 * 1024 * 1024,
			MaxCommandRequestBytes: 262144,
			TLSHandshakeTimeout:    time.Second,
			IdleConnTimeout:        time.Second,
			CapabilitiesTimeout:    time.Second,
			ReadTimeout:            time.Second,
			MutationTimeout:        time.Second,
		},
	}
}
