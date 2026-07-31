package contractprojection

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"unicode/utf8"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/shell-echo/agent/internal/runtimeport"
)

const (
	capabilitiesSchemaID  = "urn:agent-platform:agent-runtime-capabilities:v1"
	startSchemaID         = "urn:agent-platform:agent-runtime-start-request:v1"
	statusSchemaID        = "urn:agent-platform:agent-runtime-run-status:v1"
	commandSchemaID       = "urn:agent-platform:agent-runtime-command:v1"
	eventPageSchemaID     = "urn:agent-platform:agent-runtime-event-page:v1"
	standardErrorSchemaID = "urn:agent-platform:standard-error:v1"
)

var (
	ErrInvalidDocumentLimits   = errors.New("invalid runtime document limits")
	ErrInvalidRuntimeDocument  = errors.New("invalid runtime Contract document")
	ErrRegistryBindingMismatch = errors.New("runtime Event Registry binding mismatch")
)

// DocumentLimits bound parsing before Draft 2020-12 validation. The harness
// supplies the exact limits together with the locked Schema closure.
type DocumentLimits struct {
	MaxBytes            int
	MaxDepth            int
	MaxNodes            int
	MaxNumberTokenBytes int
}

func (limits DocumentLimits) Validate() error {
	if limits.MaxBytes < 1 || limits.MaxBytes > 8*1024*1024 ||
		limits.MaxDepth < 1 || limits.MaxDepth > 256 ||
		limits.MaxNodes < 1 || limits.MaxNodes > 1_000_000 ||
		limits.MaxNumberTokenBytes < 1 || limits.MaxNumberTokenBytes > 4096 {
		return ErrInvalidDocumentLimits
	}
	return nil
}

// RuntimeEventRegistryBinding is an already-admitted Provider Event Registry.
// It is validation input, not ProviderResolution or production admission.
type RuntimeEventRegistryBinding struct {
	ID      string
	Version uint64
	Digest  runtimeport.Digest
}

func (binding RuntimeEventRegistryBinding) Validate() error {
	if binding.ID == "" || len(binding.ID) > runtimeport.MaxIdentifierBytes ||
		!utf8.ValidString(binding.ID) || strings.IndexByte(binding.ID, 0) >= 0 ||
		binding.Version < 1 || binding.Version > runtimeport.MaxSafeInteger ||
		binding.Digest.Validate() != nil {
		return ErrRegistryBindingMismatch
	}
	return nil
}

// RuntimeDocumentValidator validates the exact locked Runtime transport
// documents supplied by a harness. It retains compiled validators only; it
// neither reads a Contract checkout nor copies Contract source.
type RuntimeDocumentValidator struct {
	limits     DocumentLimits
	registry   RuntimeEventRegistryBinding
	validators map[string]*jsonschema.Schema
}

func NewRuntimeDocumentValidator(
	documents []SchemaDocument,
	limits DocumentLimits,
	registry RuntimeEventRegistryBinding,
) (*RuntimeDocumentValidator, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	if err := registry.Validate(); err != nil {
		return nil, err
	}
	validators := make(map[string]*jsonschema.Schema, 6)
	for _, schemaID := range []string{
		capabilitiesSchemaID,
		startSchemaID,
		statusSchemaID,
		commandSchemaID,
		eventPageSchemaID,
		standardErrorSchemaID,
	} {
		compiled, err := CompileDraft2020(schemaID, documents)
		if err != nil {
			return nil, errors.Join(ErrInvalidRuntimeDocument, err)
		}
		validators[schemaID] = compiled
	}
	return &RuntimeDocumentValidator{
		limits:     limits,
		registry:   registry,
		validators: validators,
	}, nil
}

func (validator *RuntimeDocumentValidator) ValidateMutationRequest(
	operation runtimeport.Operation,
	invocation runtimeport.Invocation,
	encoded []byte,
) error {
	var schemaID string
	var digestField string
	switch operation {
	case runtimeport.OperationStart:
		schemaID = startSchemaID
		digestField = "request_digest"
	case runtimeport.OperationCommand:
		schemaID = commandSchemaID
		digestField = "command_digest"
	default:
		return errors.Join(ErrInvalidRuntimeDocument, runtimeport.ErrInvalidOperation)
	}
	if invocation.Operation() != operation || invocation.Validate() != nil {
		return errors.Join(ErrInvalidRuntimeDocument, runtimeport.ErrInvalidInvocation)
	}
	value, err := validator.validate(schemaID, encoded)
	if err != nil {
		return err
	}
	document, ok := value.(map[string]any)
	if !ok {
		return ErrInvalidRuntimeDocument
	}
	if stringField(document, "runtime_run_id") != invocation.RuntimeRunID() ||
		stringField(document, "invocation_id") != invocation.InvocationID() ||
		stringField(document, "invocation_attempt_id") != invocation.InvocationAttemptID() ||
		safeIntegerField(document, "fencing_token") != invocation.FencingToken() ||
		stringField(document, digestField) != string(invocation.RequestDigest()) {
		return errors.Join(ErrInvalidRuntimeDocument, runtimeport.ErrInvalidInvocation)
	}
	digest, err := excludingFieldDigest(encoded, digestField)
	if err != nil || digest != invocation.RequestDigest() {
		return errors.Join(ErrInvalidRuntimeDocument, runtimeport.ErrInvalidDigest)
	}
	return nil
}

func (validator *RuntimeDocumentValidator) ValidateSuccessResponse(
	operation runtimeport.Operation,
	encoded []byte,
) error {
	var schemaID string
	switch operation {
	case runtimeport.OperationCapabilities:
		schemaID = capabilitiesSchemaID
	case runtimeport.OperationStart, runtimeport.OperationReadStatus, runtimeport.OperationCommand:
		schemaID = statusSchemaID
	case runtimeport.OperationReadEvents:
		schemaID = eventPageSchemaID
	default:
		return errors.Join(ErrInvalidRuntimeDocument, runtimeport.ErrInvalidOperation)
	}
	value, err := validator.validate(schemaID, encoded)
	if err != nil {
		return err
	}
	if operation == runtimeport.OperationCapabilities {
		if err := validator.validateRegistry(value); err != nil {
			return err
		}
	}
	return nil
}

func (validator *RuntimeDocumentValidator) ValidateErrorResponse(encoded []byte) error {
	_, err := validator.validate(standardErrorSchemaID, encoded)
	return err
}

func (validator *RuntimeDocumentValidator) validate(schemaID string, encoded []byte) (any, error) {
	if err := validateJSONStructure(encoded, validator.limits); err != nil {
		return nil, errors.Join(ErrInvalidRuntimeDocument, err)
	}
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, errors.Join(ErrInvalidRuntimeDocument, err)
	}
	compiled := validator.validators[schemaID]
	if compiled == nil {
		return nil, ErrInvalidRuntimeDocument
	}
	if err := compiled.Validate(value); err != nil {
		return nil, errors.Join(ErrInvalidRuntimeDocument, err)
	}
	return value, nil
}

func (validator *RuntimeDocumentValidator) validateRegistry(value any) error {
	document, ok := value.(map[string]any)
	if !ok {
		return ErrRegistryBindingMismatch
	}
	items, ok := document["event_registries"].([]any)
	if !ok || len(items) != 1 {
		return ErrRegistryBindingMismatch
	}
	item, ok := items[0].(map[string]any)
	if !ok || stringField(item, "registry_id") != validator.registry.ID ||
		safeIntegerField(item, "registry_version") != validator.registry.Version ||
		stringField(item, "registry_digest") != string(validator.registry.Digest) {
		return ErrRegistryBindingMismatch
	}
	return nil
}

func validateJSONStructure(encoded []byte, limits DocumentLimits) error {
	if len(encoded) < 1 || len(encoded) > limits.MaxBytes || !utf8.Valid(encoded) {
		return ErrInvalidRuntimeDocument
	}
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.UseNumber()
	nodes := 0
	var consume func(int) error
	consume = func(depth int) error {
		if depth > limits.MaxDepth {
			return ErrInvalidRuntimeDocument
		}
		token, err := decoder.Token()
		if err != nil {
			return err
		}
		nodes++
		if nodes > limits.MaxNodes {
			return ErrInvalidRuntimeDocument
		}
		switch value := token.(type) {
		case json.Delim:
			switch value {
			case '{':
				seen := make(map[string]struct{})
				for decoder.More() {
					nameToken, err := decoder.Token()
					if err != nil {
						return err
					}
					name, ok := nameToken.(string)
					if !ok {
						return ErrInvalidRuntimeDocument
					}
					if _, exists := seen[name]; exists {
						return ErrInvalidRuntimeDocument
					}
					seen[name] = struct{}{}
					if err := consume(depth + 1); err != nil {
						return err
					}
				}
				closing, err := decoder.Token()
				if err != nil || closing != json.Delim('}') {
					return ErrInvalidRuntimeDocument
				}
			case '[':
				for decoder.More() {
					if err := consume(depth + 1); err != nil {
						return err
					}
				}
				closing, err := decoder.Token()
				if err != nil || closing != json.Delim(']') {
					return ErrInvalidRuntimeDocument
				}
			default:
				return ErrInvalidRuntimeDocument
			}
		case json.Number:
			if len(value.String()) > limits.MaxNumberTokenBytes {
				return ErrInvalidRuntimeDocument
			}
		}
		return nil
	}
	if err := consume(1); err != nil {
		return err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return ErrInvalidRuntimeDocument
	}
	return nil
}

func excludingFieldDigest(encoded []byte, field string) (runtimeport.Digest, error) {
	var document map[string]json.RawMessage
	if err := json.Unmarshal(encoded, &document); err != nil {
		return "", err
	}
	if _, exists := document[field]; !exists {
		return "", ErrInvalidRuntimeDocument
	}
	delete(document, field)
	unsigned, err := json.Marshal(document)
	if err != nil {
		return "", err
	}
	canonical, err := CanonicalizeJSON(unsigned)
	if err != nil {
		return "", err
	}
	value := fmt.Sprintf("sha256:%x", sha256.Sum256(canonical))
	return runtimeport.NewDigest(value)
}

func stringField(document map[string]any, field string) string {
	value, _ := document[field].(string)
	return value
}

func safeIntegerField(document map[string]any, field string) uint64 {
	value, ok := document[field].(json.Number)
	if !ok {
		return runtimeport.MaxSafeInteger + 1
	}
	number, err := value.Float64()
	if err != nil || number < 0 || number > float64(runtimeport.MaxSafeInteger) || number != float64(uint64(number)) {
		return runtimeport.MaxSafeInteger + 1
	}
	return uint64(number)
}
