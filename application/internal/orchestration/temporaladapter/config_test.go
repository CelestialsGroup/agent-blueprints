package temporaladapter

import (
	"errors"
	"strings"
	"testing"
)

func TestConfigValidation(t *testing.T) {
	config := testConfig()
	if err := config.Validate(); err != nil {
		t.Fatalf("validate config: %v", err)
	}

	tests := []struct {
		name   string
		mutate func(*Config)
	}{
		{"missing namespace", func(value *Config) { value.Namespace = "" }},
		{"NUL task queue", func(value *Config) { value.TaskQueue = "queue\x00bad" }},
		{"long build ID", func(value *Config) { value.WorkerBuildID = strings.Repeat("x", 201) }},
		{"invalid timeouts", func(value *Config) { value.ActivityStart = value.ActivitySchedule * 2 }},
		{"unbounded concurrency", func(value *Config) { value.MaxActivityTasks = 1001 }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			candidate := config
			test.mutate(&candidate)
			if err := candidate.Validate(); !errors.Is(err, ErrInvalidConfig) {
				t.Fatalf("Validate() error = %v, want ErrInvalidConfig", err)
			}
		})
	}
}

func testConfig() Config {
	config := DefaultConfig()
	config.Address = "temporal:7233"
	config.Namespace = "agent-b03"
	config.TaskQueue = "agent-b03-work-orders"
	config.EngineVersion = "1.29.7"
	config.WorkerDeployment = "agent-worker"
	config.WorkerBuildID = "b03.1-test-build"
	return config
}
