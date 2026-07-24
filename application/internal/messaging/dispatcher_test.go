package messaging

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

func TestDispatcherClaimsThenClassifiesAndFinalizesOutsideStoreCalls(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 2, 0, 0, 0, time.UTC)
	store := &recordingStore{
		messages: []ClaimedMessage{
			claimedMessage("succeed", 1, now.Add(time.Minute)),
			claimedMessage("retry", 1, now.Add(time.Minute)),
			claimedMessage("terminal", 1, now.Add(time.Minute)),
		},
	}
	transport := &recordingTransport{store: store}
	dispatcher, err := NewDispatcher(store, transport, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     3,
		LeaseDuration: time.Minute,
		SendTimeout:   10 * time.Second,
		RetryDelay:    5 * time.Second,
		Classify: func(err error) (FailureKind, bool) {
			if errors.Is(err, errTerminalDelivery) {
				return "terminal_delivery", true
			}
			return "retryable_delivery", false
		},
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "tenant-a")
	if err != nil {
		t.Fatalf("dispatch batch: %v", err)
	}
	if report != (DispatchReport{Claimed: 3, Succeeded: 1, RetryScheduled: 1, TerminalFailed: 1}) {
		t.Fatalf("dispatch report = %#v", report)
	}
	if got := fmt.Sprint(store.events); got != "[claim renew:succeed send:succeed ack:succeed renew:retry send:retry fail:retry:false renew:terminal send:terminal fail:terminal:true]" {
		t.Fatalf("dispatcher event order = %s", got)
	}
}

func TestDispatcherDoesNotSendAfterLeaseRenewalIsLost(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 2, 0, 0, 0, time.UTC)
	store := &recordingStore{
		messages: []ClaimedMessage{
			claimedMessage("first", 1, now.Add(time.Minute)),
			claimedMessage("lease-lost", 1, now.Add(time.Minute)),
		},
		renewErrors: map[string]error{"lease-lost": ErrLeaseLost},
	}
	dispatcher, err := NewDispatcher(store, &recordingTransport{store: store}, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     2,
		LeaseDuration: time.Minute,
		SendTimeout:   10 * time.Second,
		RetryDelay:    time.Second,
		Classify:      func(error) (FailureKind, bool) { return "delivery", false },
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "tenant-a")
	if !errors.Is(err, ErrLeaseLost) {
		t.Fatalf("dispatch with lost renewal = %v, want ErrLeaseLost", err)
	}
	if report != (DispatchReport{Claimed: 2, Succeeded: 1}) {
		t.Fatalf("dispatch report = %#v", report)
	}
	if got := fmt.Sprint(store.events); got != "[claim renew:first send:first ack:first renew:lease-lost]" {
		t.Fatalf("dispatcher sent after losing lease: %s", got)
	}
}

func TestDispatcherIncludesRenewalInTransportBudget(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 2, 0, 0, 0, time.UTC)
	store := &recordingStore{
		messages: []ClaimedMessage{
			claimedMessage("slow-renewal", 1, now.Add(time.Minute)),
		},
		renewWaitForDeadline: map[string]bool{"slow-renewal": true},
	}
	dispatcher, err := NewDispatcher(store, &recordingTransport{store: store}, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     1,
		LeaseDuration: 50 * time.Millisecond,
		SendTimeout:   time.Millisecond,
		RetryDelay:    time.Second,
		Classify:      func(error) (FailureKind, bool) { return "delivery", false },
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "tenant-a")
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("dispatch after slow renewal = %v, want context deadline exceeded", err)
	}
	if report != (DispatchReport{Claimed: 1}) {
		t.Fatalf("dispatch report = %#v", report)
	}
	if got := fmt.Sprint(store.events); got != "[claim renew:slow-renewal]" {
		t.Fatalf("dispatcher sent after renewal exhausted the attempt budget: %s", got)
	}
}

func TestDispatcherRejectsInvalidFailureKindBeforeStore(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 2, 0, 0, 0, time.UTC)
	store := &recordingStore{
		messages: []ClaimedMessage{claimedMessage("retry", 1, now.Add(time.Minute))},
	}
	dispatcher, err := NewDispatcher(store, &recordingTransport{store: store}, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     1,
		LeaseDuration: time.Minute,
		SendTimeout:   10 * time.Second,
		RetryDelay:    time.Second,
		Classify:      func(error) (FailureKind, bool) { return "Raw Provider Error", false },
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "tenant-a")
	if !errors.Is(err, ErrInvalidFailureKind) {
		t.Fatalf("dispatch with invalid failure kind = %v, want ErrInvalidFailureKind", err)
	}
	if report != (DispatchReport{Claimed: 1}) {
		t.Fatalf("dispatch report = %#v", report)
	}
	if got := fmt.Sprint(store.events); got != "[claim renew:retry send:retry]" {
		t.Fatalf("invalid failure kind reached Store: %s", got)
	}
}

func TestDispatcherRejectsInvalidClaimedBatchBeforeRenewOrSend(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 2, 0, 0, 0, time.UTC)
	invalid := claimedMessage("wrong-tenant", 1, now.Add(time.Minute))
	invalid.TenantID = "tenant-b"
	store := &recordingStore{messages: []ClaimedMessage{invalid}}
	dispatcher, err := NewDispatcher(store, &recordingTransport{store: store}, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     1,
		LeaseDuration: time.Minute,
		SendTimeout:   10 * time.Second,
		RetryDelay:    time.Second,
		Classify:      func(error) (FailureKind, bool) { return "delivery", false },
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "tenant-a")
	if !errors.Is(err, ErrInvalidMessage) {
		t.Fatalf("dispatch invalid claimed batch = %v, want ErrInvalidMessage", err)
	}
	if report != (DispatchReport{Claimed: 1}) {
		t.Fatalf("dispatch report = %#v", report)
	}
	if got := fmt.Sprint(store.events); got != "[claim]" {
		t.Fatalf("invalid claimed batch reached renewal or transport: %s", got)
	}
}

func TestDispatcherRejectsMissingTenantBeforeClaim(t *testing.T) {
	t.Parallel()

	store := &recordingStore{}
	dispatcher, err := NewDispatcher(store, &recordingTransport{store: store}, DispatcherConfig{
		WorkerID:      "worker-a",
		BatchSize:     1,
		LeaseDuration: time.Minute,
		SendTimeout:   10 * time.Second,
		RetryDelay:    time.Second,
		Classify:      func(error) (FailureKind, bool) { return "delivery", false },
	})
	if err != nil {
		t.Fatalf("create dispatcher: %v", err)
	}

	report, err := dispatcher.DispatchBatch(context.Background(), "")
	if !errors.Is(err, tenancy.ErrMissingTenantContext) {
		t.Fatalf("dispatch without TenantContext = %v, want ErrMissingTenantContext", err)
	}
	if report != (DispatchReport{}) {
		t.Fatalf("dispatch report = %#v, want empty", report)
	}
	if got := fmt.Sprint(store.events); got != "[]" {
		t.Fatalf("missing TenantContext reached Store: %s", got)
	}
}

var errTerminalDelivery = errors.New("terminal")

type recordingStore struct {
	messages             []ClaimedMessage
	events               []string
	renewErrors          map[string]error
	renewWaitForDeadline map[string]bool
}

func (store *recordingStore) Claim(
	context.Context,
	tenancy.TenantID,
	ClaimRequest,
) ([]ClaimedMessage, error) {
	store.events = append(store.events, "claim")
	return append([]ClaimedMessage(nil), store.messages...), nil
}

func (store *recordingStore) Renew(
	ctx context.Context,
	_ tenancy.TenantID,
	lease LeaseReference,
	_ time.Duration,
) error {
	store.events = append(store.events, "renew:"+lease.MessageID)
	if store.renewWaitForDeadline[lease.MessageID] {
		<-ctx.Done()
		return nil
	}
	return store.renewErrors[lease.MessageID]
}

func (store *recordingStore) Acknowledge(
	_ context.Context,
	_ tenancy.TenantID,
	lease LeaseReference,
) error {
	store.events = append(store.events, "ack:"+lease.MessageID)
	return nil
}

func (store *recordingStore) Fail(
	_ context.Context,
	_ tenancy.TenantID,
	lease LeaseReference,
	failure Failure,
) error {
	store.events = append(store.events, fmt.Sprintf("fail:%s:%t", lease.MessageID, failure.Terminal))
	return nil
}

type recordingTransport struct {
	store *recordingStore
}

func (transport *recordingTransport) Send(ctx context.Context, message ClaimedMessage) error {
	transport.store.events = append(transport.store.events, "send:"+message.MessageID)
	if _, ok := ctx.Deadline(); !ok {
		return errors.New("transport context has no deadline")
	}
	switch message.MessageID {
	case "retry":
		return errors.New("retry")
	case "terminal":
		return errTerminalDelivery
	default:
		return nil
	}
}

func claimedMessage(messageID string, fencingToken int64, leaseExpiresAt time.Time) ClaimedMessage {
	return ClaimedMessage{
		TenantID:       "tenant-a",
		MessageID:      messageID,
		Destination:    "consumer-a",
		Payload:        []byte(`{}`),
		PayloadDigest:  PayloadDigest([]byte(`{}`)),
		AttemptCount:   fencingToken,
		LeaseWorkerID:  "worker-a",
		FencingToken:   fencingToken,
		LeaseExpiresAt: leaseExpiresAt,
	}
}
