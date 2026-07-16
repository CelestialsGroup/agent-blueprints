package jcsconformance

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"strings"
)

var safeIntegerLimit = big.NewInt(9007199254740991)

// validateSafeIntegers rejects integral JSON tokens outside the interoperable
// IEEE-754 range before any float64 conversion can lose information.
func validateSafeIntegers(raw []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	for {
		token, err := decoder.Token()
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return err
		}
		number, ok := token.(json.Number)
		if !ok {
			continue
		}
		text := string(number)
		if strings.ContainsAny(text, ".eE") {
			continue
		}
		integer, ok := new(big.Int).SetString(text, 10)
		if !ok {
			return errors.New("invalid integer")
		}
		if new(big.Int).Abs(integer).Cmp(safeIntegerLimit) > 0 {
			return errors.New("integer outside interoperable IEEE-754 safe range")
		}
	}
}

func strictCanonicalize(raw []byte) ([]byte, error) {
	if err := validateSafeIntegers(raw); err != nil {
		return nil, err
	}
	return canonicalize(raw)
}
