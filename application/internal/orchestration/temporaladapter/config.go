package temporaladapter

import (
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	WorkflowType               = "agent.work-order.v1"
	ConfirmStartActivityType   = "agent.workflow-run.confirm-start.v1"
	ControlSignal              = "agent.work-order.control.v1"
	ControlComplete            = "complete"
	ControlContinueAsNew       = "continue_as_new"
	StartIdentityMemoKey       = "agent_start_identity_digest"
	EngineID                   = "temporal"
	VersioningBehavior         = "pinned"
	maxIdentifierBytes         = 200
	maxContinueAsNewGeneration = 1000
)

var ErrInvalidConfig = errors.New("invalid Temporal orchestration configuration")

// Config contains immutable worker and adapter identity plus bounded timeouts.
// Namespace and Address remain adapter-private and are never persisted.
type Config struct {
	Address           string
	Namespace         string
	TaskQueue         string
	EngineVersion     string
	WorkerDeployment  string
	WorkerBuildID     string
	WorkflowExecution time.Duration
	WorkflowRun       time.Duration
	WorkflowTask      time.Duration
	ActivitySchedule  time.Duration
	ActivityStart     time.Duration
	WorkerStop        time.Duration
	MaxWorkflowTasks  int
	MaxActivityTasks  int
}

// DefaultConfig returns bounded runtime limits without selecting a deployment endpoint.
func DefaultConfig() Config {
	return Config{
		WorkflowExecution: 24 * time.Hour,
		WorkflowRun:       24 * time.Hour,
		WorkflowTask:      10 * time.Second,
		ActivitySchedule:  2 * time.Minute,
		ActivityStart:     15 * time.Second,
		WorkerStop:        30 * time.Second,
		MaxWorkflowTasks:  32,
		MaxActivityTasks:  16,
	}
}

// Validate rejects missing, unbounded, or unsafe adapter configuration.
func (config Config) Validate() error {
	identifiers := []struct {
		name  string
		value string
	}{
		{"address", config.Address},
		{"namespace", config.Namespace},
		{"task queue", config.TaskQueue},
		{"engine version", config.EngineVersion},
		{"worker deployment", config.WorkerDeployment},
		{"worker build ID", config.WorkerBuildID},
	}
	for _, identifier := range identifiers {
		if err := validateIdentifier(identifier.value); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrInvalidConfig, identifier.name, err)
		}
	}
	if len(config.EngineVersion) > 64 {
		return fmt.Errorf("%w: engine version exceeds 64 bytes", ErrInvalidConfig)
	}
	if config.WorkflowExecution <= 0 || config.WorkflowRun <= 0 || config.WorkflowTask <= 0 ||
		config.ActivitySchedule <= 0 || config.ActivityStart <= 0 || config.WorkerStop <= 0 {
		return fmt.Errorf("%w: timeouts must be positive", ErrInvalidConfig)
	}
	if config.WorkflowRun > config.WorkflowExecution {
		return fmt.Errorf("%w: workflow run timeout exceeds execution timeout", ErrInvalidConfig)
	}
	if config.ActivityStart > config.ActivitySchedule {
		return fmt.Errorf("%w: activity start timeout exceeds schedule timeout", ErrInvalidConfig)
	}
	if config.MaxWorkflowTasks <= 0 || config.MaxWorkflowTasks > 1000 ||
		config.MaxActivityTasks <= 0 || config.MaxActivityTasks > 1000 {
		return fmt.Errorf("%w: worker concurrency must be between 1 and 1000", ErrInvalidConfig)
	}
	return nil
}

func validateIdentifier(value string) error {
	if value == "" {
		return errors.New("value is required")
	}
	if len(value) > maxIdentifierBytes {
		return fmt.Errorf("value exceeds %d bytes", maxIdentifierBytes)
	}
	if !utf8.ValidString(value) || strings.IndexByte(value, 0) >= 0 {
		return errors.New("value must be valid UTF-8 without NUL")
	}
	return nil
}
