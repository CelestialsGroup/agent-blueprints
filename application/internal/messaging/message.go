package messaging

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

const (
	MaxEncodedPayloadBytes = 1 << 20
	MaxBatchSize           = 100
	MaxLeaseDuration       = 5 * time.Minute
	MaxRetryDelay          = 24 * time.Hour
)

var (
	ErrInvalidMessage       = errors.New("invalid durable message")
	ErrPayloadTooLarge      = errors.New("durable message payload exceeds the storage limit")
	ErrOutboxConflict       = errors.New("outbox message identity conflict")
	ErrInboxConflict        = errors.New("inbox message identity conflict")
	ErrInboxDigestConflict  = errors.New("inbox message digest conflict")
	ErrLeaseLost            = errors.New("outbox lease is missing, expired, or fenced")
	ErrMessagingNotFound    = errors.New("durable message not found")
	ErrInvalidFailureKind   = errors.New("invalid durable message failure kind")
	ErrInvalidLease         = errors.New("invalid durable message lease")
	ErrInvalidDispatchBatch = errors.New("invalid dispatcher batch")
)

type OutboxState string

const (
	OutboxPending        OutboxState = "pending"
	OutboxLeased         OutboxState = "leased"
	OutboxSucceeded      OutboxState = "succeeded"
	OutboxTerminalFailed OutboxState = "terminal_failed"
)

type EnqueueOutcome string

const (
	EnqueueInserted EnqueueOutcome = "inserted"
	EnqueueReplay   EnqueueOutcome = "replay"
)

type ConsumeOutcome string

const (
	ConsumeApplied ConsumeOutcome = "applied"
	ConsumeReplay  ConsumeOutcome = "replay"
)

type OutboundMessage struct {
	MessageID     string
	Destination   string
	Payload       []byte
	PayloadDigest string
	AvailableAt   time.Time
	CreatedAt     time.Time
}

func NewOutboundMessage(
	messageID string,
	destination string,
	payload []byte,
	availableAt time.Time,
	createdAt time.Time,
) (OutboundMessage, error) {
	message := OutboundMessage{
		MessageID:     messageID,
		Destination:   destination,
		Payload:       append([]byte(nil), payload...),
		PayloadDigest: PayloadDigest(payload),
		AvailableAt:   availableAt.UTC(),
		CreatedAt:     createdAt.UTC(),
	}
	if err := message.Validate(); err != nil {
		return OutboundMessage{}, err
	}
	return message, nil
}

func (message OutboundMessage) Validate() error {
	if err := ValidateMessageID(message.MessageID); err != nil {
		return err
	}
	if err := validateIdentifier("destination", message.Destination, 200); err != nil {
		return err
	}
	if len(message.Payload) == 0 {
		return fmt.Errorf("%w: payload is empty", ErrInvalidMessage)
	}
	if len(message.Payload) > MaxEncodedPayloadBytes {
		return fmt.Errorf("%w: got %d bytes, maximum is %d", ErrPayloadTooLarge, len(message.Payload), MaxEncodedPayloadBytes)
	}
	if message.PayloadDigest != PayloadDigest(message.Payload) {
		return fmt.Errorf("%w: payload_digest does not match payload", ErrInvalidMessage)
	}
	if message.CreatedAt.IsZero() || message.AvailableAt.IsZero() || message.AvailableAt.Before(message.CreatedAt) {
		return fmt.Errorf("%w: invalid message timestamps", ErrInvalidMessage)
	}
	return nil
}

type InboundMessage struct {
	Consumer      string
	MessageID     string
	Payload       []byte
	PayloadDigest string
	ReceivedAt    time.Time
}

func NewInboundMessage(
	tenantID tenancy.TenantID,
	consumer string,
	messageID string,
	payload []byte,
	receivedAt time.Time,
) (InboundMessage, error) {
	message := InboundMessage{
		Consumer:      consumer,
		MessageID:     messageID,
		Payload:       append([]byte(nil), payload...),
		PayloadDigest: PayloadDigest(payload),
		ReceivedAt:    receivedAt.UTC(),
	}
	if err := message.Validate(tenantID); err != nil {
		return InboundMessage{}, err
	}
	return message, nil
}

func (message InboundMessage) Validate(tenantID tenancy.TenantID) error {
	if err := tenantID.Validate(); err != nil {
		return err
	}
	if err := validateIdentifier("consumer", message.Consumer, 200); err != nil {
		return err
	}
	if err := ValidateMessageID(message.MessageID); err != nil {
		return err
	}
	if len(message.Payload) == 0 {
		return fmt.Errorf("%w: payload is empty", ErrInvalidMessage)
	}
	if len(message.Payload) > MaxEncodedPayloadBytes {
		return fmt.Errorf("%w: got %d bytes, maximum is %d", ErrPayloadTooLarge, len(message.Payload), MaxEncodedPayloadBytes)
	}
	if message.PayloadDigest != PayloadDigest(message.Payload) {
		return fmt.Errorf("%w: payload_digest does not match payload", ErrInvalidMessage)
	}
	if message.ReceivedAt.IsZero() {
		return fmt.Errorf("%w: received_at is required", ErrInvalidMessage)
	}
	return nil
}

type LeaseReference struct {
	MessageID    string
	WorkerID     string
	FencingToken int64
}

func (lease LeaseReference) Validate() error {
	if err := ValidateMessageID(lease.MessageID); err != nil {
		return errors.Join(ErrInvalidLease, err)
	}
	if err := validateIdentifier("worker_id", lease.WorkerID, 200); err != nil {
		return errors.Join(ErrInvalidLease, err)
	}
	if lease.FencingToken < 1 {
		return fmt.Errorf("%w: fencing_token must be positive", ErrInvalidLease)
	}
	return nil
}

type ClaimRequest struct {
	WorkerID      string
	BatchSize     int32
	LeaseDuration time.Duration
}

func (request ClaimRequest) Validate() error {
	if err := validateIdentifier("worker_id", request.WorkerID, 200); err != nil {
		return errors.Join(ErrInvalidDispatchBatch, err)
	}
	if request.BatchSize < 1 || request.BatchSize > MaxBatchSize {
		return fmt.Errorf("%w: batch_size must be between 1 and %d", ErrInvalidDispatchBatch, MaxBatchSize)
	}
	if request.LeaseDuration < time.Microsecond ||
		request.LeaseDuration > MaxLeaseDuration ||
		request.LeaseDuration%time.Microsecond != 0 {
		return fmt.Errorf(
			"%w: lease_duration must be a whole number of microseconds between %s and %s",
			ErrInvalidDispatchBatch,
			time.Microsecond,
			MaxLeaseDuration,
		)
	}
	return nil
}

type ClaimedMessage struct {
	TenantID       tenancy.TenantID
	MessageID      string
	Destination    string
	Payload        []byte
	PayloadDigest  string
	AttemptCount   int64
	LeaseWorkerID  string
	FencingToken   int64
	LeaseExpiresAt time.Time
}

func (message ClaimedMessage) Validate(tenantID tenancy.TenantID, workerID string) error {
	if err := tenantID.Validate(); err != nil {
		return err
	}
	if message.TenantID != tenantID {
		return fmt.Errorf("%w: claimed message tenant differs from TenantContext", ErrInvalidMessage)
	}
	if err := validateIdentifier("destination", message.Destination, 200); err != nil {
		return err
	}
	if len(message.Payload) == 0 {
		return fmt.Errorf("%w: claimed payload is empty", ErrInvalidMessage)
	}
	if len(message.Payload) > MaxEncodedPayloadBytes {
		return fmt.Errorf("%w: got %d bytes, maximum is %d", ErrPayloadTooLarge, len(message.Payload), MaxEncodedPayloadBytes)
	}
	if message.PayloadDigest != PayloadDigest(message.Payload) {
		return fmt.Errorf("%w: claimed payload_digest does not match payload", ErrInvalidMessage)
	}
	if message.LeaseWorkerID != workerID {
		return fmt.Errorf("%w: claimed message worker differs from dispatcher", ErrInvalidLease)
	}
	if message.AttemptCount < 1 || message.AttemptCount != message.FencingToken {
		return fmt.Errorf("%w: claimed attempt and fencing token are inconsistent", ErrInvalidLease)
	}
	if message.LeaseExpiresAt.IsZero() {
		return fmt.Errorf("%w: claimed lease expiry is required", ErrInvalidLease)
	}
	return message.LeaseReference().Validate()
}

func (message ClaimedMessage) LeaseReference() LeaseReference {
	return LeaseReference{
		MessageID:    message.MessageID,
		WorkerID:     message.LeaseWorkerID,
		FencingToken: message.FencingToken,
	}
}

type OutboxStatus struct {
	TenantID         tenancy.TenantID
	MessageID        string
	State            OutboxState
	AttemptCount     int64
	FencingToken     int64
	LeaseWorkerID    string
	LeaseExpiresAt   time.Time
	NextAttemptAt    time.Time
	LastErrorKind    FailureKind
	SucceededAt      time.Time
	TerminalFailedAt time.Time
}

type Failure struct {
	Kind       FailureKind
	Terminal   bool
	RetryDelay time.Duration
}

func (failure Failure) Validate() error {
	if err := failure.Kind.Validate(); err != nil {
		return err
	}
	if failure.Terminal && failure.RetryDelay != 0 {
		return fmt.Errorf("%w: terminal failure cannot have a retry delay", ErrInvalidFailureKind)
	}
	if !failure.Terminal && (failure.RetryDelay < 0 ||
		failure.RetryDelay > MaxRetryDelay ||
		failure.RetryDelay%time.Microsecond != 0) {
		return fmt.Errorf(
			"%w: retry_delay must be a whole number of microseconds between 0 and %s",
			ErrInvalidFailureKind,
			MaxRetryDelay,
		)
	}
	return nil
}

type FailureKind string

func (kind FailureKind) Validate() error {
	value := string(kind)
	if len(value) == 0 || len(value) > 200 {
		return fmt.Errorf("%w: error_kind must contain between 1 and 200 ASCII characters", ErrInvalidFailureKind)
	}
	for index, character := range []byte(value) {
		if character >= 'a' && character <= 'z' {
			continue
		}
		if index > 0 && ((character >= '0' && character <= '9') || character == '_') {
			continue
		}
		return fmt.Errorf("%w: error_kind must match [a-z][a-z0-9_]*", ErrInvalidFailureKind)
	}
	return nil
}

func ValidateMessageID(messageID string) error {
	return validateIdentifier("message_id", messageID, 200)
}

func PayloadDigest(payload []byte) string {
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func validateIdentifier(name string, value string, maximumCharacters int) error {
	if value == "" ||
		!utf8.ValidString(value) ||
		strings.IndexByte(value, 0) >= 0 ||
		utf8.RuneCountInString(value) > maximumCharacters {
		return fmt.Errorf(
			"%w: %s must be valid UTF-8 without NUL between 1 and %d characters",
			ErrInvalidMessage,
			name,
			maximumCharacters,
		)
	}
	return nil
}
