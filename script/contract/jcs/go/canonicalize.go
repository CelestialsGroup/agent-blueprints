package jcsconformance

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
)

func hexValue(value byte) (uint16, bool) {
	switch {
	case value >= '0' && value <= '9':
		return uint16(value - '0'), true
	case value >= 'a' && value <= 'f':
		return uint16(value-'a') + 10, true
	case value >= 'A' && value <= 'F':
		return uint16(value-'A') + 10, true
	default:
		return 0, false
	}
}

func readUnicodeEscape(raw []byte, start int) (uint16, error) {
	if start+4 > len(raw) {
		return 0, errors.New("truncated Unicode escape")
	}
	var value uint16
	for index := start; index < start+4; index++ {
		digit, ok := hexValue(raw[index])
		if !ok {
			return 0, errors.New("invalid Unicode escape")
		}
		value = value*16 + digit
	}
	return value, nil
}

func validateRawSurrogates(raw []byte) error {
	inString := false
	for index := 0; index < len(raw); index++ {
		switch raw[index] {
		case '"':
			inString = !inString
		case '\\':
			if !inString || index+1 >= len(raw) {
				continue
			}
			index++
			if raw[index] != 'u' {
				continue
			}
			value, err := readUnicodeEscape(raw, index+1)
			if err != nil {
				return err
			}
			index += 4
			if value >= 0xd800 && value <= 0xdbff {
				if index+6 >= len(raw) || raw[index+1] != '\\' || raw[index+2] != 'u' {
					return errors.New("lone high surrogate")
				}
				low, err := readUnicodeEscape(raw, index+3)
				if err != nil || low < 0xdc00 || low > 0xdfff {
					return errors.New("invalid surrogate pair")
				}
				index += 6
			} else if value >= 0xdc00 && value <= 0xdfff {
				return errors.New("lone low surrogate")
			}
		}
	}
	return nil
}

type objectMember struct {
	name  string
	value string
	key   []uint16
}

func numberToJSON(value float64) (string, error) {
	bits := math.Float64bits(value)
	if bits&0x7ff0000000000000 == 0x7ff0000000000000 {
		return "", errors.New("invalid JSON number")
	}
	if value == 0 {
		return "0", nil
	}

	sign := ""
	if value < 0 {
		value = -value
		sign = "-"
	}

	format := byte('e')
	if value < 1e21 && value >= 1e-6 {
		format = 'f'
	}
	formatted := strconv.FormatFloat(value, format, -1, 64)
	if exponent := strings.IndexByte(formatted, 'e'); exponent > 0 {
		if exponent+2 < len(formatted) && formatted[exponent+2] == '0' {
			formatted = formatted[:exponent+2] + formatted[exponent+3:]
		}
	}
	return sign + formatted, nil
}

func quoteString(value string) string {
	var result strings.Builder
	result.WriteByte('"')
	for _, r := range value {
		switch r {
		case '"':
			result.WriteString(`\"`)
		case '\\':
			result.WriteString(`\\`)
		case '\b':
			result.WriteString(`\b`)
		case '\f':
			result.WriteString(`\f`)
		case '\n':
			result.WriteString(`\n`)
		case '\r':
			result.WriteString(`\r`)
		case '\t':
			result.WriteString(`\t`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&result, `\u%04x`, r)
			} else {
				result.WriteRune(r)
			}
		}
	}
	result.WriteByte('"')
	return result.String()
}

func compareUTF16(left, right []uint16) int {
	length := len(left)
	if len(right) < length {
		length = len(right)
	}
	for index := 0; index < length; index++ {
		if left[index] < right[index] {
			return -1
		}
		if left[index] > right[index] {
			return 1
		}
	}
	switch {
	case len(left) < len(right):
		return -1
	case len(left) > len(right):
		return 1
	default:
		return 0
	}
}

func parseValue(decoder *json.Decoder) (string, error) {
	token, err := decoder.Token()
	if err != nil {
		return "", err
	}

	switch value := token.(type) {
	case nil:
		return "null", nil
	case bool:
		if value {
			return "true", nil
		}
		return "false", nil
	case string:
		return quoteString(value), nil
	case json.Number:
		floatValue, err := strconv.ParseFloat(string(value), 64)
		if err != nil {
			return "", err
		}
		return numberToJSON(floatValue)
	case json.Delim:
		switch value {
		case '[':
			var elements []string
			for decoder.More() {
				element, err := parseValue(decoder)
				if err != nil {
					return "", err
				}
				elements = append(elements, element)
			}
			end, err := decoder.Token()
			if err != nil || end != json.Delim(']') {
				return "", errors.New("invalid array termination")
			}
			return "[" + strings.Join(elements, ",") + "]", nil

		case '{':
			var members []objectMember
			seen := map[string]struct{}{}
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return "", err
				}
				name, ok := keyToken.(string)
				if !ok {
					return "", errors.New("object member name is not a string")
				}
				if _, exists := seen[name]; exists {
					return "", fmt.Errorf("duplicate object member: %s", name)
				}
				seen[name] = struct{}{}

				canonicalValue, err := parseValue(decoder)
				if err != nil {
					return "", err
				}
				members = append(members, objectMember{
					name:  name,
					value: canonicalValue,
					key:   utf16.Encode([]rune(name)),
				})
			}
			end, err := decoder.Token()
			if err != nil || end != json.Delim('}') {
				return "", errors.New("invalid object termination")
			}

			sort.Slice(members, func(i, j int) bool {
				return compareUTF16(members[i].key, members[j].key) < 0
			})
			var result strings.Builder
			result.WriteByte('{')
			for index, member := range members {
				if index > 0 {
					result.WriteByte(',')
				}
				result.WriteString(quoteString(member.name))
				result.WriteByte(':')
				result.WriteString(member.value)
			}
			result.WriteByte('}')
			return result.String(), nil
		}
	}
	return "", fmt.Errorf("unsupported JSON token: %T", token)
}

func canonicalize(raw []byte) ([]byte, error) {
	if err := validateRawSurrogates(raw); err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()

	value, err := parseValue(decoder)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		if err == nil {
			return nil, errors.New("multiple top-level JSON values")
		}
		return nil, err
	}
	return []byte(value), nil
}
