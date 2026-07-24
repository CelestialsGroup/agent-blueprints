package messaging

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

func TestOutboundMessageEnforcesEncodedPayloadLimit(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 1, 0, 0, 0, time.UTC)
	_, err := NewOutboundMessage(
		"message-too-large",
		"consumer-a",
		[]byte(strings.Repeat("x", MaxEncodedPayloadBytes+1)),
		now,
		now,
	)
	if !errors.Is(err, ErrPayloadTooLarge) {
		t.Fatalf("oversized payload = %v, want ErrPayloadTooLarge", err)
	}
}

func TestMessageIDUsesPostgreSQLCharacterSemantics(t *testing.T) {
	t.Parallel()

	if err := ValidateMessageID(strings.Repeat("界", 200)); err != nil {
		t.Fatalf("validate 200-character message ID: %v", err)
	}
	if err := ValidateMessageID(strings.Repeat("界", 201)); !errors.Is(err, ErrInvalidMessage) {
		t.Fatalf("validate 201-character message ID = %v, want ErrInvalidMessage", err)
	}
	if err := ValidateMessageID("message\x00id"); !errors.Is(err, ErrInvalidMessage) {
		t.Fatalf("validate NUL message ID = %v, want ErrInvalidMessage", err)
	}
}

func TestLeaseAndRetryDurationsAreBounded(t *testing.T) {
	t.Parallel()

	validClaim := ClaimRequest{WorkerID: "worker-a", BatchSize: 1, LeaseDuration: MaxLeaseDuration}
	if err := validClaim.Validate(); err != nil {
		t.Fatalf("validate maximum lease: %v", err)
	}
	invalidClaim := validClaim
	invalidClaim.LeaseDuration += time.Microsecond
	if err := invalidClaim.Validate(); !errors.Is(err, ErrInvalidDispatchBatch) {
		t.Fatalf("validate oversized lease = %v, want ErrInvalidDispatchBatch", err)
	}
	invalidClaim.LeaseDuration = time.Microsecond + time.Nanosecond
	if err := invalidClaim.Validate(); !errors.Is(err, ErrInvalidDispatchBatch) {
		t.Fatalf("validate sub-microsecond lease precision = %v, want ErrInvalidDispatchBatch", err)
	}

	if err := (Failure{Kind: "retry", RetryDelay: MaxRetryDelay}).Validate(); err != nil {
		t.Fatalf("validate maximum retry delay: %v", err)
	}
	if err := (Failure{Kind: "retry", RetryDelay: MaxRetryDelay + time.Microsecond}).Validate(); !errors.Is(err, ErrInvalidFailureKind) {
		t.Fatalf("validate oversized retry delay = %v, want ErrInvalidFailureKind", err)
	}
	if err := (Failure{Kind: "retry", RetryDelay: time.Nanosecond}).Validate(); !errors.Is(err, ErrInvalidFailureKind) {
		t.Fatalf("validate sub-microsecond retry precision = %v, want ErrInvalidFailureKind", err)
	}
	if err := (Failure{Kind: "terminal", Terminal: true, RetryDelay: time.Second}).Validate(); !errors.Is(err, ErrInvalidFailureKind) {
		t.Fatalf("validate terminal retry delay = %v, want ErrInvalidFailureKind", err)
	}
	for _, kind := range []FailureKind{
		"Raw Provider Error",
		"dependency.unavailable",
		"_leading_underscore",
		FailureKind("non_ascii_" + string(rune(0x00e9))),
		FailureKind(strings.Repeat("a", 201)),
	} {
		if err := (Failure{Kind: kind, RetryDelay: time.Second}).Validate(); !errors.Is(err, ErrInvalidFailureKind) {
			t.Errorf("validate error kind %q = %v, want ErrInvalidFailureKind", kind, err)
		}
	}
}

func TestInboundMessageCopiesPayload(t *testing.T) {
	t.Parallel()

	tenantID := tenancy.TenantID("tenant-a")
	payload := []byte(`{"value":1}`)
	message, err := NewInboundMessage(
		tenantID,
		"consumer-a",
		"message-a",
		payload,
		time.Date(2026, time.July, 23, 1, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatalf("create inbound message: %v", err)
	}
	payload[0] = 'x'
	if string(message.Payload) != `{"value":1}` {
		t.Fatalf("message payload mutated through caller storage: %s", message.Payload)
	}
}
