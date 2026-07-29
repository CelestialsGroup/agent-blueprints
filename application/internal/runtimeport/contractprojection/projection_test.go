package contractprojection

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/go-jose/go-jose/v4"
	"github.com/shell-echo/agent/internal/generated/runtimeapi"
)

type fixtureManifest struct {
	Positive [][2]string `json:"positive"`
	Negative [][2]string `json:"negative"`
}

type projectionManifest struct {
	Schemas []struct {
		Path string `json:"path"`
		ID   string `json:"id"`
	} `json:"schemas"`
}

func contractRoot(t *testing.T) string {
	t.Helper()
	if configured := os.Getenv("AGENT_CONTRACT_ROOT"); configured != "" {
		return configured
	}
	root, err := filepath.Abs(filepath.Join("..", "..", "..", "..", "contract"))
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func applicationRoot(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func readJSON(t *testing.T, path string, target any) {
	t.Helper()
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(encoded, target); err != nil {
		t.Fatal(err)
	}
}

func schemaDocuments(t *testing.T) []SchemaDocument {
	t.Helper()
	var manifest projectionManifest
	readJSON(
		t,
		filepath.Join(applicationRoot(t), "internal", "generated", "runtimeapi", "projection-manifest.json"),
		&manifest,
	)
	documents := make([]SchemaDocument, 0, len(manifest.Schemas))
	for _, item := range manifest.Schemas {
		var document any
		readJSON(t, filepath.Join(contractRoot(t), filepath.FromSlash(item.Path)), &document)
		documents = append(documents, SchemaDocument{ID: item.ID, Document: document})
	}
	return documents
}

func TestLockedRuntimeFixturesHaveDraft2020Parity(t *testing.T) {
	var fixtures fixtureManifest
	readJSON(
		t,
		filepath.Join(applicationRoot(t), "test", "conformance", "runtime-contract-fixtures.json"),
		&fixtures,
	)
	documents := schemaDocuments(t)
	validators := make(map[string]interface{ Validate(any) error })
	validate := func(t *testing.T, fixture [2]string, expectedValid bool) {
		t.Helper()
		validator := validators[fixture[1]]
		if validator == nil {
			compiled, err := CompileDraft2020(fixture[1], documents)
			if err != nil {
				t.Fatal(err)
			}
			validator = compiled
			validators[fixture[1]] = validator
		}
		var value any
		readJSON(t, filepath.Join(contractRoot(t), filepath.FromSlash(fixture[0])), &value)
		err := validator.Validate(value)
		if expectedValid && err != nil {
			t.Fatalf("expected %s to be valid against %s: %v", fixture[0], fixture[1], err)
		}
		if !expectedValid && err == nil {
			t.Fatalf("expected %s to be rejected by %s", fixture[0], fixture[1])
		}
	}
	for _, fixture := range fixtures.Positive {
		t.Run("positive/"+filepath.Base(fixture[0]), func(t *testing.T) { validate(t, fixture, true) })
	}
	for _, fixture := range fixtures.Negative {
		t.Run("negative/"+filepath.Base(fixture[0]), func(t *testing.T) { validate(t, fixture, false) })
	}
}

func TestGeneratedTransportUnmarshalsLockedCapability(t *testing.T) {
	encoded, err := os.ReadFile(filepath.Join(contractRoot(t), "examples", "contracts", "agent-runtime-capabilities.json"))
	if err != nil {
		t.Fatal(err)
	}
	var capability runtimeapi.AgentRuntimeCapabilities
	if err := json.Unmarshal(encoded, &capability); err != nil {
		t.Fatal(err)
	}
	if capability.ProtocolVersion != "v1" {
		t.Fatalf("unexpected protocol version: %s", capability.ProtocolVersion)
	}
}

func TestJCSMatchesLockedVectors(t *testing.T) {
	var vectors struct {
		Valid []struct {
			ID        string `json:"id"`
			Input     string `json:"input"`
			Canonical string `json:"canonical"`
		} `json:"valid"`
	}
	readJSON(t, filepath.Join(contractRoot(t), "testdata", "jcs-v1", "vectors.json"), &vectors)
	for _, vector := range vectors.Valid {
		t.Run(vector.ID, func(t *testing.T) {
			canonical, err := CanonicalizeJSON([]byte(vector.Input))
			if err != nil {
				t.Fatal(err)
			}
			if string(canonical) != vector.Canonical {
				t.Fatalf("canonical form mismatch\nwant: %s\n got: %s", vector.Canonical, canonical)
			}
		})
	}
}

func TestJOSEAllowlistSupportsEdDSAAndES256(t *testing.T) {
	payload := []byte(`{"contract":"runtime-core-v1"}`)
	_, edPrivate, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ecPrivate, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name       string
		algorithm  jose.SignatureAlgorithm
		signingKey any
		verifyKey  any
	}{
		{name: "EdDSA", algorithm: jose.EdDSA, signingKey: edPrivate, verifyKey: edPrivate.Public()},
		{name: "ES256", algorithm: jose.ES256, signingKey: ecPrivate, verifyKey: &ecPrivate.PublicKey},
	} {
		t.Run(test.name, func(t *testing.T) {
			options := (&jose.SignerOptions{}).
				WithType("agent-runtime-invocation+jwt").
				WithHeader(jose.HeaderKey("kid"), "test-key")
			signer, err := jose.NewSigner(
				jose.SigningKey{Algorithm: test.algorithm, Key: test.signingKey},
				options,
			)
			if err != nil {
				t.Fatal(err)
			}
			signed, err := signer.Sign(payload)
			if err != nil {
				t.Fatal(err)
			}
			compact, err := signed.CompactSerialize()
			if err != nil {
				t.Fatal(err)
			}
			verified, err := VerifyAllowedSignature(compact, test.verifyKey)
			if err != nil {
				t.Fatal(err)
			}
			if string(verified) != string(payload) {
				t.Fatal("verified payload differs")
			}
		})
	}
}

func TestJOSEAllowlistCannotBeMutatedToAcceptHS256(t *testing.T) {
	algorithms := allowedSignatureAlgorithms()
	algorithms[0] = jose.HS256

	signer, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.HS256, Key: []byte("01234567890123456789012345678901")},
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	signed, err := signer.Sign([]byte("not-admitted"))
	if err != nil {
		t.Fatal(err)
	}
	compact, err := signed.CompactSerialize()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := VerifyAllowedSignature(compact, []byte("01234567890123456789012345678901")); err == nil {
		t.Fatal("HS256 must be rejected before signature verification")
	}
}
