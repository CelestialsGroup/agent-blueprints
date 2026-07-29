package contractprojection

import (
	"fmt"

	"github.com/go-jose/go-jose/v4"
	"github.com/gowebpki/jcs"
	"github.com/santhosh-tekuri/jsonschema/v6"
)

func allowedSignatureAlgorithms() []jose.SignatureAlgorithm {
	return []jose.SignatureAlgorithm{jose.EdDSA, jose.ES256}
}

type SchemaDocument struct {
	ID       string
	Document any
}

func CompileDraft2020(rootID string, documents []SchemaDocument) (*jsonschema.Schema, error) {
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft2020)
	compiler.AssertFormat()
	for _, document := range documents {
		if document.ID == "" {
			return nil, fmt.Errorf("schema document ID is required")
		}
		if err := compiler.AddResource(document.ID, document.Document); err != nil {
			return nil, fmt.Errorf("add schema resource %s: %w", document.ID, err)
		}
	}
	schema, err := compiler.Compile(rootID)
	if err != nil {
		return nil, fmt.Errorf("compile Draft 2020-12 schema %s: %w", rootID, err)
	}
	return schema, nil
}

func CanonicalizeJSON(encoded []byte) ([]byte, error) {
	canonical, err := jcs.Transform(encoded)
	if err != nil {
		return nil, fmt.Errorf("canonicalize RFC 8785 JSON: %w", err)
	}
	return canonical, nil
}

func VerifyAllowedSignature(compact string, verificationKey any) ([]byte, error) {
	signed, err := jose.ParseSignedCompact(compact, allowedSignatureAlgorithms())
	if err != nil {
		return nil, fmt.Errorf("parse allowlisted compact JWS: %w", err)
	}
	payload, err := signed.Verify(verificationKey)
	if err != nil {
		return nil, fmt.Errorf("verify compact JWS: %w", err)
	}
	return payload, nil
}
