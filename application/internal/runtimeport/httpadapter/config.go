// Package httpadapter provides the harness-only Agent Runtime HTTPS adapter.
// No production composition root imports or constructs this package.
package httpadapter

import (
	"crypto/tls"
	"errors"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/shell-echo/agent/internal/runtimeport"
)

var ErrInvalidConfiguration = errors.New("invalid Runtime HTTP adapter configuration")

// ContractValidator is required because generated DTO decoding alone does not
// prove the locked Draft 2020-12 closure or Runtime Event Registry binding.
type ContractValidator interface {
	ValidateMutationRequest(runtimeport.Operation, runtimeport.Invocation, []byte) error
	ValidateSuccessResponse(runtimeport.Operation, []byte) error
	ValidateErrorResponse([]byte) error
}

type Limits struct {
	MaxConnections         int
	MaxResponseHeaderBytes int64
	MaxResponseBytes       int64
	MaxTokenBytes          int
	MaxStartRequestBytes   int
	MaxCommandRequestBytes int
	TLSHandshakeTimeout    time.Duration
	IdleConnTimeout        time.Duration
	CapabilitiesTimeout    time.Duration
	ReadTimeout            time.Duration
	MutationTimeout        time.Duration
}

func (limits Limits) Validate() error {
	if limits.MaxConnections < 1 || limits.MaxConnections > 128 ||
		limits.MaxResponseHeaderBytes < 1024 || limits.MaxResponseHeaderBytes > 65536 ||
		limits.MaxResponseBytes < 256 || limits.MaxResponseBytes > 1024*1024 ||
		limits.MaxTokenBytes < 1 || limits.MaxTokenBytes > 1024*1024 ||
		limits.MaxStartRequestBytes < 1 || limits.MaxStartRequestBytes > 8*1024*1024 ||
		limits.MaxCommandRequestBytes < 1 || limits.MaxCommandRequestBytes > 262144 {
		return ErrInvalidConfiguration
	}
	for _, timeout := range []time.Duration{
		limits.TLSHandshakeTimeout,
		limits.IdleConnTimeout,
		limits.CapabilitiesTimeout,
		limits.ReadTimeout,
		limits.MutationTimeout,
	} {
		if timeout < 50*time.Millisecond || timeout > 5*time.Minute {
			return ErrInvalidConfiguration
		}
	}
	return nil
}

type Configuration struct {
	Endpoint           string
	ProviderRevisionID string
	Client             *http.Client
	Validator          ContractValidator
	Limits             Limits
}

// Adapter owns only immutable transport configuration and a canonical
// Capabilities digest. It owns no endpoint resolution, token issuance, or
// durable reconciliation state.
type Adapter struct {
	endpoint           *url.URL
	providerRevisionID string
	client             *http.Client
	validator          ContractValidator
	limits             Limits

	capabilitiesMu     sync.Mutex
	capabilitiesDigest [32]byte
	capabilitiesSeen   bool
}

func New(configuration Configuration) (*Adapter, error) {
	if configuration.Validator == nil || configuration.Client == nil || configuration.Limits.Validate() != nil {
		return nil, ErrInvalidConfiguration
	}
	if _, err := runtimeport.NewCapabilitiesRequest(configuration.ProviderRevisionID); err != nil {
		return nil, ErrInvalidConfiguration
	}
	endpoint, err := url.Parse(configuration.Endpoint)
	if err != nil || endpoint.Scheme != "https" || endpoint.Host == "" || endpoint.Hostname() == "" ||
		endpoint.Opaque != "" || endpoint.User != nil || endpoint.ForceQuery ||
		(endpoint.Path != "" && endpoint.Path != "/") || endpoint.RawPath != "" ||
		endpoint.RawQuery != "" || endpoint.Fragment != "" {
		return nil, ErrInvalidConfiguration
	}
	transport, ok := configuration.Client.Transport.(*http.Transport)
	if !ok || transport == nil || transport.Proxy != nil || hasCustomDial(transport) ||
		transport.TLSNextProto != nil || transport.GetProxyConnectHeader != nil ||
		transport.ProxyConnectHeader != nil || configuration.Client.Timeout != 0 ||
		configuration.Client.Jar != nil {
		return nil, ErrInvalidConfiguration
	}
	tlsConfiguration := transport.TLSClientConfig
	if tlsConfiguration == nil || tlsConfiguration.InsecureSkipVerify || tlsConfiguration.RootCAs == nil ||
		tlsConfiguration.MinVersion < tls.VersionTLS12 ||
		(tlsConfiguration.MaxVersion != 0 && tlsConfiguration.MaxVersion < tlsConfiguration.MinVersion) ||
		!hasClientIdentity(tlsConfiguration) {
		return nil, ErrInvalidConfiguration
	}

	clonedTransport := transport.Clone()
	clonedTransport.Proxy = nil
	clonedTransport.DisableCompression = true
	clonedTransport.DisableKeepAlives = true
	clonedTransport.ForceAttemptHTTP2 = false
	clonedTransport.MaxConnsPerHost = configuration.Limits.MaxConnections
	clonedTransport.MaxIdleConns = 0
	clonedTransport.MaxIdleConnsPerHost = 0
	clonedTransport.MaxResponseHeaderBytes = configuration.Limits.MaxResponseHeaderBytes
	clonedTransport.TLSHandshakeTimeout = configuration.Limits.TLSHandshakeTimeout
	clonedTransport.IdleConnTimeout = configuration.Limits.IdleConnTimeout
	clonedTransport.ExpectContinueTimeout = 0
	clonedTransport.ResponseHeaderTimeout = 0
	clonedTransport.TLSClientConfig = tlsConfiguration.Clone()
	clonedTransport.TLSClientConfig.NextProtos = []string{"http/1.1"}

	clonedClient := *configuration.Client
	clonedClient.Transport = clonedTransport
	clonedClient.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}

	endpoint.Path = ""
	return &Adapter{
		endpoint:           endpoint,
		providerRevisionID: configuration.ProviderRevisionID,
		client:             &clonedClient,
		validator:          configuration.Validator,
		limits:             configuration.Limits,
	}, nil
}

func hasCustomDial(transport *http.Transport) bool {
	//lint:ignore SA1019 strict configuration must reject the legacy override too
	legacyDial := transport.Dial != nil
	//lint:ignore SA1019 strict configuration must reject the legacy override too
	legacyTLSDial := transport.DialTLS != nil
	return legacyDial || transport.DialContext != nil || legacyTLSDial || transport.DialTLSContext != nil
}

func hasClientIdentity(configuration *tls.Config) bool {
	if configuration.GetClientCertificate != nil {
		return true
	}
	for _, certificate := range configuration.Certificates {
		if len(certificate.Certificate) > 0 && len(certificate.Certificate[0]) > 0 && certificate.PrivateKey != nil {
			return true
		}
	}
	return false
}
