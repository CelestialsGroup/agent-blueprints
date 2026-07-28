package temporaladapter

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

type nativeExecutionReference struct {
	Namespace  string `json:"namespace"`
	RunID      string `json:"run_id"`
	WorkflowID string `json:"workflow_id"`
}

func workflowID(workOrderID string) (string, error) {
	if err := validateIdentifier(workOrderID); err != nil {
		return "", fmt.Errorf("invalid WorkOrder ID: %w", err)
	}
	value := "work-order/" + workOrderID
	if len(value) > maxIdentifierBytes {
		return "", fmt.Errorf("stable Workflow ID exceeds %d bytes", maxIdentifierBytes)
	}
	return value, nil
}

func digestNativeExecution(namespace, temporalWorkflowID, runID string) (string, error) {
	for name, value := range map[string]string{
		"namespace":   namespace,
		"workflow ID": temporalWorkflowID,
		"run ID":      runID,
	} {
		if err := validateIdentifier(value); err != nil {
			return "", fmt.Errorf("invalid native %s: %w", name, err)
		}
	}
	payload, err := json.Marshal(nativeExecutionReference{
		Namespace: namespace, RunID: runID, WorkflowID: temporalWorkflowID,
	})
	if err != nil {
		return "", fmt.Errorf("encode native execution reference: %w", err)
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}
