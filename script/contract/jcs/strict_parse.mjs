const SAFE_INTEGER_MAX = 9007199254740991n;
const MAX_NUMBER_TOKEN_LENGTH = 1024;
const MAX_ABS_DECIMAL_EXPONENT = 400;

function exactIntegerValue(token) {
  const negative = token.startsWith("-");
  const unsigned = negative ? token.slice(1) : token;
  const [mantissa, exponentText] = unsigned.toLowerCase().split("e");
  const exponent = exponentText === undefined ? 0 : Number(exponentText);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > MAX_ABS_DECIMAL_EXPONENT) {
    throw new SyntaxError("JSON number exponent exceeds admission resource limit");
  }
  const [whole, fraction = ""] = mantissa.split(".");
  const coefficient = BigInt(`${whole}${fraction}`);
  const scale = exponent - fraction.length;
  let integer;
  if (scale >= 0) {
    integer = coefficient * (10n ** BigInt(scale));
  } else {
    const divisor = 10n ** BigInt(-scale);
    if (coefficient % divisor !== 0n) return null;
    integer = coefficient / divisor;
  }
  return negative ? -integer : integer;
}

function rejectLoneSurrogates(value) {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new SyntaxError("Lone high surrogate");
      }
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw new SyntaxError("Lone low surrogate");
    }
  }
}

export function strictParse(raw) {
  let offset = 0;

  function fail(message) {
    throw new SyntaxError(`${message} at byte ${offset}`);
  }

  function skipWhitespace() {
    while (offset < raw.length && /[\t\n\r ]/.test(raw[offset])) offset += 1;
  }

  function parseString() {
    const start = offset;
    if (raw[offset] !== '"') fail("Expected string");
    offset += 1;
    while (offset < raw.length) {
      const code = raw.charCodeAt(offset);
      if (code === 0x22) {
        offset += 1;
        const value = JSON.parse(raw.slice(start, offset));
        rejectLoneSurrogates(value);
        return value;
      }
      if (code < 0x20) fail("Unescaped control character");
      if (code === 0x5c) {
        offset += 1;
        if (offset >= raw.length) fail("Truncated escape");
        if (raw[offset] === "u") {
          const digits = raw.slice(offset + 1, offset + 5);
          if (!/^[0-9a-fA-F]{4}$/.test(digits)) fail("Invalid Unicode escape");
          offset += 5;
          continue;
        }
        if (!/["\\/bfnrt]/.test(raw[offset])) fail("Invalid escape");
      }
      offset += 1;
    }
    fail("Unterminated string");
  }

  function parseNumber() {
    const match = raw.slice(offset).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    if (!match) fail("Invalid number");
    const token = match[0];
    if (token.length > MAX_NUMBER_TOKEN_LENGTH) fail("JSON number token exceeds admission resource limit");
    offset += token.length;
    const number = Number(token);
    if (!Number.isFinite(number)) fail("Non-finite number");
    const integer = exactIntegerValue(token);
    if (integer !== null) {
      if (integer > SAFE_INTEGER_MAX || integer < -SAFE_INTEGER_MAX) {
        fail("Integer exceeds interoperable IEEE-754 safe range");
      }
    }
  }

  function parseArray() {
    offset += 1;
    skipWhitespace();
    if (raw[offset] === "]") {
      offset += 1;
      return;
    }
    while (true) {
      parseValue();
      skipWhitespace();
      if (raw[offset] === "]") {
        offset += 1;
        return;
      }
      if (raw[offset] !== ",") fail("Expected ',' or ']'");
      offset += 1;
      skipWhitespace();
    }
  }

  function parseObject() {
    offset += 1;
    const keys = new Set();
    skipWhitespace();
    if (raw[offset] === "}") {
      offset += 1;
      return;
    }
    while (true) {
      const key = parseString();
      if (keys.has(key)) fail(`Duplicate object member: ${key}`);
      keys.add(key);
      skipWhitespace();
      if (raw[offset] !== ":") fail("Expected ':'");
      offset += 1;
      parseValue();
      skipWhitespace();
      if (raw[offset] === "}") {
        offset += 1;
        return;
      }
      if (raw[offset] !== ",") fail("Expected ',' or '}'");
      offset += 1;
      skipWhitespace();
    }
  }

  function parseValue() {
    skipWhitespace();
    const current = raw[offset];
    if (current === "{") return parseObject();
    if (current === "[") return parseArray();
    if (current === '"') return void parseString();
    if (current === "-" || /[0-9]/.test(current ?? "")) return parseNumber();
    for (const literal of ["true", "false", "null"]) {
      if (raw.startsWith(literal, offset)) {
        offset += literal.length;
        return;
      }
    }
    fail("Invalid JSON value");
  }

  if (typeof raw !== "string") throw new TypeError("strictParse expects raw JSON text");
  parseValue();
  skipWhitespace();
  if (offset !== raw.length) fail("Trailing JSON content");
  return JSON.parse(raw);
}
