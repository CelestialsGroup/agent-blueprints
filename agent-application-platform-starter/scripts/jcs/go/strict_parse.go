package jcsconformance

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"strconv"
	"strings"
)

var safeIntegerLimit = big.NewInt(9007199254740991)

func exactIntegerToken(raw string) (*big.Int, bool, error) {
	negative := strings.HasPrefix(raw, "-")
	if negative {
		raw = raw[1:]
	}
	exponent := 0
	if index := strings.IndexAny(raw, "eE"); index >= 0 {
		parsed, err := strconv.Atoi(raw[index+1:])
		if err != nil {
			return nil, false, err
		}
		exponent = parsed
		raw = raw[:index]
	}
	fractionDigits := 0
	if index := strings.IndexByte(raw, '.'); index >= 0 {
		fractionDigits = len(raw) - index - 1
		raw = raw[:index] + raw[index+1:]
	}
	coefficient, ok := new(big.Int).SetString(raw, 10)
	if !ok {
		return nil, false, errors.New("invalid JSON number coefficient")
	}
	scale := exponent - fractionDigits
	if scale >= 0 {
		factor := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(scale)), nil)
		coefficient.Mul(coefficient, factor)
	} else {
		divisor := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(-scale)), nil)
		quotient, remainder := new(big.Int), new(big.Int)
		quotient.QuoRem(coefficient, divisor, remainder)
		if remainder.Sign() != 0 {
			return nil, false, nil
		}
		coefficient = quotient
	}
	if negative {
		coefficient.Neg(coefficient)
	}
	return coefficient, true, nil
}

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
		_, err = strconv.ParseFloat(string(number), 64)
		if err != nil {
			return err
		}
		integer, integral, err := exactIntegerToken(string(number))
		if err != nil {
			return err
		}
		if !integral {
			continue
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
