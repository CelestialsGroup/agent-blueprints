package main

import (
	"strings"
	"testing"
)

func TestLoadConfig(t *testing.T) {
	values := validProcessEnvironment()
	config, err := loadConfig(func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	})
	if err != nil {
		t.Fatalf("load process config: %v", err)
	}
	if config.databaseDSN != values["AGENT_DATABASE_DSN"] ||
		config.temporal.Address != values["AGENT_TEMPORAL_ADDRESS"] ||
		config.temporal.WorkerBuildID != values["AGENT_WORKER_BUILD_ID"] {
		t.Fatalf("loaded process config does not match environment: %#v", config)
	}
}

func TestLoadConfigFailsClosedInStableOrder(t *testing.T) {
	if _, err := loadConfig(nil); err == nil {
		t.Fatal("nil environment lookup was accepted")
	}

	values := validProcessEnvironment()
	delete(values, "AGENT_DATABASE_DSN")
	delete(values, "AGENT_TEMPORAL_ADDRESS")
	if _, err := loadConfig(func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}); err == nil || !strings.Contains(err.Error(), "AGENT_DATABASE_DSN is required") {
		t.Fatalf("first missing configuration error = %v", err)
	}

	values = validProcessEnvironment()
	values["AGENT_TEMPORAL_NAMESPACE"] = "invalid\x00namespace"
	if _, err := loadConfig(func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}); err == nil || !strings.Contains(err.Error(), "AGENT_TEMPORAL_NAMESPACE is invalid") {
		t.Fatalf("invalid configuration error = %v", err)
	}
}

func validProcessEnvironment() map[string]string {
	return map[string]string{
		"AGENT_DATABASE_DSN":            "postgres://agent:password@postgres/agent",
		"AGENT_TEMPORAL_ADDRESS":        "temporal:7233",
		"AGENT_TEMPORAL_NAMESPACE":      "default",
		"AGENT_TEMPORAL_TASK_QUEUE":     "agent-work-orders",
		"AGENT_TEMPORAL_ENGINE_VERSION": "1.29.7",
		"AGENT_WORKER_DEPLOYMENT":       "agent-worker",
		"AGENT_WORKER_BUILD_ID":         "b03.1-test",
	}
}
