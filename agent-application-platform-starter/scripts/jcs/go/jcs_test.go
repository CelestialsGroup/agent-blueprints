package jcsconformance

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

type vectorFile struct {
	Valid []struct {
		ID        string `json:"id"`
		Input     string `json:"input"`
		Canonical string `json:"canonical"`
	} `json:"valid"`
	Invalid []struct {
		ID    string `json:"id"`
		Input string `json:"input"`
	} `json:"invalid"`
}

func loadVectors(t *testing.T) vectorFile {
	t.Helper()
	_, current, _, _ := runtime.Caller(0)
	path := filepath.Join(
		filepath.Dir(current),
		"..", "..", "..",
		"contracts", "testdata", "jcs-v1", "vectors.json",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var vectors vectorFile
	if err := json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	return vectors
}

func TestRFC8785ValidVectors(t *testing.T) {
	for _, vector := range loadVectors(t).Valid {
		actual, err := canonicalize([]byte(vector.Input))
		if err != nil {
			t.Fatalf("%s: %v", vector.ID, err)
		}
		if string(actual) != vector.Canonical {
			t.Fatalf(
				"%s: expected %q, got %q",
				vector.ID,
				vector.Canonical,
				string(actual),
			)
		}
	}
}

func TestParserLevelInvalidVectors(t *testing.T) {
	for _, vector := range loadVectors(t).Invalid {
		switch vector.ID {
		case "nan", "positive-infinity", "duplicate-key", "lone-surrogate":
			if _, err := canonicalize([]byte(vector.Input)); err == nil {
				t.Fatalf("%s: expected failure", vector.ID)
			}
		}
	}
}
